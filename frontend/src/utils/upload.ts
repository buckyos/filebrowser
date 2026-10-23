import { useLayoutStore } from "@/stores/layout";
import { useUploadStore } from "@/stores/upload";
import url from "@/utils/url";

export function checkConflict(
  files: UploadList,
  dest: ResourceItem[]
): boolean {
  if (typeof dest === "undefined" || dest === null) {
    dest = [];
  }

  if (files.length === 0) return false;
  const folder_upload = files[0].fullPath !== undefined;

  const names = new Set<string>();
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    let name = file.name;

    if (folder_upload) {
      const dirs = file.fullPath?.split("/");
      if (dirs && dirs.length > 1) {
        name = dirs[0];
      }
    }

    names.add(name);
  }

  return dest.some((d) => names.has(d.name));
}

export async function scanFiles(dt: DataTransfer): Promise<UploadList> {
  const entries = [...dt.items].filter(item => item.kind === "file").map(item => ({ entry: item.webkitGetAsEntry?.(), file: item.getAsFile() }));
  const contents: UploadList = [];
  const read = async (entry: FileSystemEntry, directory = ""): Promise<void> => {
    const fullPath = `${directory}${entry.name}`;
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      contents.push({ file, name: file.name, size: file.size, isDir: false, fullPath });
    } else if (entry.isDirectory) {
      contents.push({ name: entry.name, size: 0, isDir: true, fullPath });
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const children = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
        if (children.length === 0) break;
        for (const child of children) await read(child, `${fullPath}/`);
      }
    } else throw new Error(`Cannot read dropped entry: ${fullPath}`);
  };
  if (entries.length === 0) return [...dt.files].map(file => ({ file, name: file.name, size: file.size, isDir: false }));
  for (const item of entries) {
    if (item.entry) await read(item.entry);
    else if (item.file) contents.push({ file: item.file, name: item.file.name, size: item.file.size, isDir: false });
    else throw new Error("A dropped entry could not be read");
  }
  return contents;
}

function detectType(mimetype: string): ResourceType {
  if (mimetype.startsWith("video")) return "video";
  if (mimetype.startsWith("audio")) return "audio";
  if (mimetype.startsWith("image")) return "image";
  if (mimetype.startsWith("pdf")) return "pdf";
  if (mimetype.startsWith("text")) return "text";
  return "blob";
}

export function handleFiles(
  files: UploadList,
  base: string,
  overwrite = false
) {
  const uploadStore = useUploadStore();
  const layoutStore = useLayoutStore();

  layoutStore.closeHovers();

  const roots = new Map<string, NamedUploadTree>();
  const singleFiles: UploadEntry[] = [];
  for (const item of files) {
    const segments = (item.fullPath ?? item.name).split("/");
    if (segments.some(name => !name || name === "." || name === ".." || /[\\\0:]/.test(name))) throw new Error("Invalid upload path");
    if (segments.length === 1 && !item.isDir) { singleFiles.push(item); continue; }
    const rootName = segments.shift()!;
    let root = roots.get(rootName);
    if (!root) { root = { kind: "dir", name: rootName, children: [] }; roots.set(rootName, root); }
    let parent = root;
    const directorySegments = item.isDir ? segments : segments.slice(0, -1);
    for (const name of directorySegments) {
      let child = parent.children.find(child => (child.kind === "dir" ? child.name : child.file.name) === name);
      if (child?.kind === "file") throw new Error(`A file blocks directory ${name}`);
      if (!child) { child = { kind: "dir", name, children: [] }; parent.children.push(child); }
      parent = child;
    }
    if (!item.isDir) {
      const file = item.file!;
      if (parent.children.some(child => (child.kind === "dir" ? child.name : child.file.name) === file.name)) throw new Error(`Duplicate upload name: ${file.name}`);
      parent.children.push({ kind: "file", file });
    }
  }
  for (const file of singleFiles) {
    if (roots.has(file.name)) throw new Error(`A file conflicts with folder ${file.name}`);
    uploadStore.upload(base + url.encodeRFC5987ValueChars(file.name), file.name, file.file!, overwrite, detectType(file.file!.type));
  }
  for (const tree of roots.values()) uploadStore.upload(base + url.encodeRFC5987ValueChars(tree.name), tree.name, null, overwrite, "dir", tree);
}
