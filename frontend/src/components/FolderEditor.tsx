import React, { useState } from 'react';
import { FolderRead, updateFolder, moveFolder, isApiError } from '../services/api';
import { validateName, validateRelativePath } from '../utils/path';
import './FolderEditor.css';

type EditorMode = 'rename' | 'move';

interface Props {
  folder: FolderRead;
  onUpdated: (folder: FolderRead) => void;
  onCancel: () => void;
  defaultMode?: 'rename' | 'move';
}

const FolderEditor: React.FC<Props> = ({ folder, onUpdated, onCancel, defaultMode = 'rename' }) => {
  const [mode, setMode] = useState<EditorMode>(defaultMode);
  const [newName, setNewName] = useState(folder.name);
  const [newNameError, setNewNameError] = useState<string | null>(null);
  const [newRelPath, setNewRelPath] = useState(folder.relative_path);
  const [newNameForMove, setNewNameForMove] = useState(folder.name);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleNameChange = (value: string) => {
    setNewName(value);
    setNewNameError(validateName(value));
  };

  const handleRelPathChange = (value: string) => {
    setNewRelPath(value);
    setMoveError(validateRelativePath(value));
  };

  const handleNameForMoveChange = (value: string) => {
    setNewNameForMove(value);
  };

  const handleSaveRename = async () => {
    const err = validateName(newName);
    if (err) {
      setNewNameError(err);
      return;
    }

    setIsSaving(true);
    try {
      const res = await updateFolder(folder.id, { name: newName });
      onUpdated(res.data);
    } catch (e) {
      if (isApiError(e)) {
        setNewNameError(e.response.data.message || 'An error occurred.');
      } else {
        setNewNameError('Cannot connect to server.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveMove = async () => {
    const relErr = validateRelativePath(newRelPath);
    if (relErr) {
      setMoveError(relErr);
      return;
    }
    const nameErr = validateName(newNameForMove);
    if (nameErr) {
      setMoveError(nameErr);
      return;
    }

    setIsSaving(true);
    setMoveError(null);
    try {
      const res = await moveFolder(folder.id, {
        new_relative_path: newRelPath,
        new_name: newNameForMove,
      });
      onUpdated(res.data);
    } catch (e) {
      if (isApiError(e)) {
        setMoveError(e.response.data.message || 'An error occurred.');
      } else {
        setMoveError('Cannot connect to server.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSave = () => {
    if (mode === 'rename') {
      handleSaveRename();
    } else {
      handleSaveMove();
    }
  };

  const canSaveRename = newName !== folder.name && !newNameError && !isSaving;
  const canSaveMove =
    (newRelPath !== folder.relative_path || newNameForMove !== folder.name) &&
    !moveError &&
    !isSaving;

  return (
    <div className="folder-editor">
      <div className="mode-switcher">
        <button
          type="button"
          className={mode === 'rename' ? 'active' : ''}
          onClick={() => setMode('rename')}
          disabled={isSaving}
        >
          Rename
        </button>
        <button
          type="button"
          className={mode === 'move' ? 'active' : ''}
          onClick={() => setMode('move')}
          disabled={isSaving}
        >
          Move / Edit Path
        </button>
      </div>

      {mode === 'rename' && (
        <div className="editor-field">
          <label>New Name</label>
          <input
            type="text"
            value={newName}
            onChange={(e) => handleNameChange(e.target.value)}
            disabled={isSaving}
            className={newNameError ? 'invalid' : ''}
          />
          {newNameError && <span className="error-msg">{newNameError}</span>}
        </div>
      )}

      {mode === 'move' && (
        <>
          <div className="editor-field">
            <label>New Folder Name</label>
            <input
              type="text"
              value={newNameForMove}
              onChange={(e) => handleNameForMoveChange(e.target.value)}
              disabled={isSaving}
            />
          </div>
          <div className="editor-field">
            <label>New Relative Path</label>
            <input
              type="text"
              value={newRelPath}
              onChange={(e) => handleRelPathChange(e.target.value)}
              disabled={isSaving}
              className={moveError ? 'invalid' : ''}
              placeholder="e.g. parent/child/new_folder"
            />
            {moveError && <span className="error-msg">{moveError}</span>}
          </div>
          <p className="hint">
            Path relative to the SMB root. The parent directory must exist on
            disk.
          </p>
        </>
      )}

      <div className="editor-actions">
        <button onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
        <button
          className="primary"
          onClick={handleSave}
          disabled={
            isSaving ||
            (mode === 'rename' ? !canSaveRename : !canSaveMove)
          }
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  );
};

export default FolderEditor;
