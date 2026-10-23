import { buckyos, getActiveSessionToken, ndm } from "buckyos";
import { useAuthStore } from "@/stores/auth";
import { baseURL } from "@/utils/constants";
import { fetchURL, removePrefix } from "./utils";

let initialized: Promise<void> | undefined;

async function zoneToken() {
  initialized ??= buckyos.initBuckyOS("filebrowser").catch(error => { initialized = undefined; throw error; });
  await initialized;
  const token = await getActiveSessionToken() ?? (await buckyos.login())?.session_token;
  if (!token) throw new Error("Sign in to your BuckyOS Zone before importing files");
  return token;
}

export async function importUpload(upload: Upload, signal: AbortSignal, progress: (loaded: number) => void) {
  const sessionToken = await zoneToken();
  const options = {
    endpoint: `${window.location.origin}${baseURL}/api`,
    sessionToken,
    headers: { "X-Auth": useAuthStore().jwt },
    signal,
    autoStartUpload: false,
  };
  if (!upload.importSession) {
    const snapshot = upload.tree
      ? await ndm.importDirectory(upload.tree, options)
      : await ndm.importFiles([upload.file!], { ...options, mode: "single_file" });
    upload.importSession = snapshot.sessionId;
    upload.objectId = snapshot.items[0]?.objectId;
  }
  const status = await ndm.ensureUploaded(upload.importSession, { ...options, onProgress: value => progress(value.uploadedBytes) });
  if (status.objectStatus !== "ready" || !upload.objectId) throw new Error("The imported object is not ready");
  if (signal.aborted) throw new Error("Upload aborted");
  await fetchURL(`/api/objects${removePrefix(upload.path)}?override=${upload.overwrite}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${sessionToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ obj_id: upload.objectId }),
    signal,
  });
  ndm.releaseImportSession(upload.importSession);
  upload.importSession = undefined;
}

export function releaseUpload(upload: Upload) {
  if (upload.importSession) ndm.releaseImportSession(upload.importSession);
  upload.file = null;
  upload.tree = undefined;
}
