type NamedUploadTree = { kind: "dir"; name: string; children: ({ kind: "file"; file: File } | NamedUploadTree)[] };

type Upload = {
  status: "pending" | "uploading" | "success" | "failed" | "cancelled";
  error?: string;
  tree?: NamedUploadTree;
  importSession?: string;
  objectId?: string;
  path: string;
  name: string;
  file: File | null;
  type: ResourceType;
  overwrite: boolean;
  totalBytes: number;
  sentBytes: number;
  rawProgress: {
    sentBytes: number;
  };
};

interface UploadEntry {
  name: string;
  size: number;
  isDir: boolean;
  fullPath?: string;
  file?: File;
}

type UploadList = UploadEntry[];
