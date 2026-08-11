import React, { useEffect, useState } from 'react';
import { fetchEvents, FolderEventRead } from '../services/api';
import './EventHistory.css';

interface Props {
  folderId?: number;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  created: 'Created',
  deleted: 'Deleted',
  modified: 'Modified',
  renamed: 'Renamed',
  moved: 'Moved',
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  created: '#22c55e',
  deleted: '#ef4444',
  modified: '#f59e0b',
  renamed: '#3b82f6',
  moved: '#8b5cf6',
};

const EventHistory: React.FC<Props> = ({ folderId }) => {
  const [events, setEvents] = useState<FolderEventRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadEvents = async () => {
    setLoading(true);
    try {
      const params: any = { limit: 100 };
      if (folderId) params.folder_id = folderId;
      const res = await fetchEvents(params);
      setEvents(res.data);
      setError(null);
    } catch (err) {
      setError('Cannot load event history.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderId]);

  if (loading) {
    return <div className="event-history">Loading history...</div>;
  }

  if (error) {
    return <div className="event-history error">{error}</div>;
  }

  if (!events.length) {
    return <div className="event-history empty">No events yet.</div>;
  }

  return (
    <div className="event-history">
      <h3>Event History</h3>
      <div className="event-table">
        <div className="event-header">
          <div className="col-time">Time</div>
          <div className="col-type">Type</div>
          <div className="col-folder">Folder</div>
          <div className="col-user">Source</div>
        </div>
        {events.map((evt) => (
          <div key={evt.id} className="event-row">
            <div className="col-time">
              {new Date(evt.detected_at).toLocaleString('en-US')}
            </div>
            <div
              className="col-type badge"
              style={{
                backgroundColor:
                  EVENT_TYPE_COLORS[evt.event_type] + '20',
                color: EVENT_TYPE_COLORS[evt.event_type],
              }}
            >
              {EVENT_TYPE_LABELS[evt.event_type] || evt.event_type}
            </div>
            <div className="col-folder">
              {evt.old_name && evt.new_name
                ? `${evt.old_name} -> ${evt.new_name}`
                : evt.new_name || evt.old_name || ''}
            </div>
            <div className="col-user">{evt.source || ''}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EventHistory;
