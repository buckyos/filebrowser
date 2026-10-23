import { defineStore } from "pinia";
import { useFileStore } from "./file";
import { importUpload, releaseUpload } from "@/api/namedUpload";
import buttons from "@/utils/buttons";
import url from "@/utils/url";
import { computed, inject, markRaw, ref } from "vue";


// TODO: make this into a user setting
const UPLOADS_LIMIT = 5;

function treeSize(tree: NamedUploadTree): number {
  return tree.children.reduce((sum, item) => sum + (item.kind === "file" ? item.file.size : treeSize(item)), 0);
}

const beforeUnload = (event: Event) => {
  event.preventDefault();
  // To remove >> is deprecated
  // event.returnValue = "";
};

export const useUploadStore = defineStore("upload", () => {
  const $showError = inject<IToastError>("$showError")!;

  let progressInterval: number | null = null;

  //
  // STATE
  //

  const allUploads = ref<Upload[]>([]);
  const activeUploads = ref<Set<Upload>>(new Set());
  const lastUpload = ref<number>(-1);
  const totalBytes = ref<number>(0);
  const sentBytes = ref<number>(0);
  const lastBatch = ref({ success: 0, failed: 0, cancelled: 0 });
  const failedUploads = ref<Upload[]>([]);
  const controllers = new Map<Upload, AbortController>();

  //
  // ACTIONS
  //

  const upload = (
    path: string,
    name: string,
    file: File | null,
    overwrite: boolean,
    type: ResourceType,
    tree?: NamedUploadTree
  ) => {
    if (!hasActiveUploads() && !hasPendingUploads()) {
      window.addEventListener("beforeunload", beforeUnload);
      buttons.loading("upload");
    }

    const upload: Upload = {
      status: "pending",
      tree,
      path,
      name,
      file,
      overwrite,
      type,
      totalBytes: tree ? treeSize(tree) : file?.size ?? 0,
      sentBytes: 0,
      // Stores rapidly changing sent bytes value without causing component re-renders
      rawProgress: markRaw({
        sentBytes: 0,
      }),
    };

    totalBytes.value += upload.totalBytes;
    allUploads.value.push(upload);

    processUploads();
  };

  const abort = () => {
    // Resets the state by preventing the processing of the remaning uploads
    for (const item of allUploads.value) {
      if (item.status === "pending") item.status = "cancelled";
    }
    lastUpload.value = allUploads.value.length - 1;
    for (const controller of controllers.values()) controller.abort();
    void processUploads();
  };

  //
  // GETTERS
  //

  const pendingUploadCount = computed(
    () =>
      allUploads.value.length -
      (lastUpload.value + 1) +
      activeUploads.value.size
  );

  //
  // PRIVATE FUNCTIONS
  //

  const hasActiveUploads = () => activeUploads.value.size > 0;

  const hasPendingUploads = () =>
    allUploads.value.length > lastUpload.value + 1;

  const isActiveUploadsOnLimit = () => activeUploads.value.size < UPLOADS_LIMIT;

  const processUploads = async () => {
    if (!hasActiveUploads() && !hasPendingUploads()) {
      const fileStore = useFileStore();
      window.removeEventListener("beforeunload", beforeUnload);
      lastBatch.value = {
        success: allUploads.value.filter(item => item.status === "success").length,
        failed: allUploads.value.filter(item => item.status === "failed").length,
        cancelled: allUploads.value.filter(item => item.status === "cancelled").length,
      };
      if (lastBatch.value.failed || lastBatch.value.cancelled) buttons.done("upload");
      else buttons.success("upload");
      failedUploads.value.push(...allUploads.value.filter(item => item.status === "failed" || item.status === "cancelled"));
      reset();
      fileStore.reload = true;
    }

    if (isActiveUploadsOnLimit() && hasPendingUploads()) {
      if (!hasActiveUploads()) {
        // Update the state in a fixed time interval
        progressInterval = window.setInterval(syncState, 1000);
      }

      const upload = nextUpload();

      const controller = new AbortController();
      controllers.set(upload, controller);
      try {
        await importUpload(upload, controller.signal, loaded => { upload.rawProgress.sentBytes = loaded; });
        upload.status = "success";
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        upload.status = controller.signal.aborted ? "cancelled" : "failed";
        upload.error = message;
        if (upload.status === "failed") $showError(message);
      } finally {
        controllers.delete(upload);
      }

      finishUpload(upload);
    }
  };

  const nextUpload = (): Upload => {
    lastUpload.value++;

    const upload = allUploads.value[lastUpload.value];
    upload.status = "uploading";
    activeUploads.value.add(upload);

    return upload;
  };

  const finishUpload = (upload: Upload) => {
    if (upload.status === "success") {
      sentBytes.value += upload.totalBytes - upload.sentBytes;
      upload.sentBytes = upload.totalBytes;
    }
    if (upload.status === "success") { upload.file = null; upload.tree = undefined; }

    activeUploads.value.delete(upload);
    processUploads();
  };

  const syncState = () => {
    for (const upload of activeUploads.value) {
      sentBytes.value += upload.rawProgress.sentBytes - upload.sentBytes;
      upload.sentBytes = upload.rawProgress.sentBytes;
    }
  };

  const reset = () => {
    if (progressInterval !== null) {
      clearInterval(progressInterval);
      progressInterval = null;
    }

    allUploads.value = [];
    activeUploads.value = new Set();
    lastUpload.value = -1;
    totalBytes.value = 0;
    sentBytes.value = 0;
  };

  const dismissFailed = () => {
    for (const item of failedUploads.value) releaseUpload(item);
    failedUploads.value = [];
  };

  const retryFailed = () => {
    const retry = failedUploads.value.splice(0);
    for (const item of retry) {
      item.status = "pending";
      item.sentBytes = 0;
      item.rawProgress.sentBytes = 0;
      allUploads.value.push(item);
      totalBytes.value += item.totalBytes;
    }
    if (retry.length) { buttons.loading("upload"); window.addEventListener("beforeunload", beforeUnload); void processUploads(); }
  };

  const retryWithName = (item: Upload, name: string) => {
    if (!name || name === "." || name === ".." || /[/\\\0:]/.test(name)) { $showError("Invalid destination name"); return; }
    const index = failedUploads.value.indexOf(item);
    if (index < 0) return;
    failedUploads.value.splice(index, 1);
    item.path = item.path.slice(0, item.path.lastIndexOf("/") + 1) + url.encodeRFC5987ValueChars(name);
    item.name = name;
    item.overwrite = false;
    item.status = "pending";
    item.sentBytes = item.rawProgress.sentBytes = 0;
    allUploads.value.push(item);
    totalBytes.value += item.totalBytes;
    buttons.loading("upload");
    window.addEventListener("beforeunload", beforeUnload);
    void processUploads();
  };

  return {
    // STATE
    activeUploads,
    totalBytes,
    sentBytes,

    // ACTIONS
    upload,
    abort,

    // GETTERS
    pendingUploadCount,
    lastBatch,
    failedUploads,
    retryFailed,
    retryWithName,
    dismissFailed,
  };
});
