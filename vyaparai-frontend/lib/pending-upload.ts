// Module-level singleton — holds a CSV file between the POS step and the
// business step so we can upload it after the business_id is created.
let _pendingFile: File | null = null;

export function setPendingUpload(file: File | null) {
  _pendingFile = file;
}

export function getPendingUpload(): File | null {
  return _pendingFile;
}
