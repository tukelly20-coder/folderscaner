export function validateName(name: string): string | null {
  if (!name || name.trim() === '') {
    return 'Folder name cannot be empty.';
  }
  const invalidChars = '<>:"/\\|?*'.split('');
  const found = invalidChars.filter((c) => name.includes(c));
  if (found.length > 0) {
    return `Folder name contains invalid characters: ${found.join(' ')}`;
  }
  if (name !== name.trim()) {
    return 'Folder name cannot start or end with whitespace.';
  }
  if (name.endsWith('.') || name.endsWith(' ')) {
    return 'Folder name cannot end with a dot or space.';
  }
  return null;
}

export function validateRelativePath(relPath: string): string | null {
  if (!relPath || relPath.trim() === '') {
    return 'Relative path cannot be empty.';
  }
  if (relPath.startsWith('/') || relPath.startsWith('\\')) {
    return 'Relative path must not be absolute.';
  }
  if (relPath.length >= 2 && relPath[1] === ':') {
    return 'Relative path must not contain a drive letter.';
  }
  const segments = relPath.replace(/\\/g, '/').split('/').filter((s) => s !== '');
  if (segments.some((s) => s === '..')) {
    return 'Relative path cannot contain ".." segments.';
  }
  for (const seg of segments) {
    const err = validateName(seg);
    if (err) return err;
  }
  return null;
}

export function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+/g, '/');
}

export function getParentPath(relPath: string): string {
  const normalized = normalizePath(relPath);
  const parts = normalized.split('/').filter((s) => s !== '');
  parts.pop();
  return parts.join('/');
}
