import { authFetch } from './authFetch';

export interface FileAsset {
  id: string;
  fileName: string;
  contentType: string | null;
  size: number;
  createdAt: string;
}

export async function listFiles(): Promise<FileAsset[]> {
  const response = await authFetch('/files');
  if (!response.ok) {
    throw new Error(`Failed to list files (${response.status})`);
  }
  return response.json();
}

export async function uploadFile(file: Blob, fileName: string): Promise<FileAsset> {
  const formData = new FormData();
  formData.append('file', file, fileName);
  const response = await authFetch('/files', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Failed to upload file (${response.status})`);
  }
  return response.json();
}

export async function deleteFile(id: string): Promise<void> {
  const response = await authFetch(`/files/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(`Failed to delete file (${response.status})`);
  }
}

export async function fetchFileBlob(id: string): Promise<Blob> {
  const response = await authFetch(`/files/${id}/download`);
  if (!response.ok) {
    throw new Error(`Failed to download file (${response.status})`);
  }
  return response.blob();
}
