import type { LogEntry } from "../../api/types";
import { EmptyState } from "../layout/StateBlocks";
import { JsonBlock } from "./JsonBlock";

interface LogsPanelProps {
  logs: LogEntry[];
}

function getLogMessage(log: LogEntry): string {
  if (typeof log === "string") {
    return log;
  }

  if (typeof log.message === "string") {
    return log.message;
  }

  return JSON.stringify(log) ?? "Log entry";
}

export function LogsPanel({ logs }: LogsPanelProps) {
  if (logs.length === 0) {
    return <EmptyState title="No logs yet" message="The backend returned an empty log list." />;
  }

  return (
    <ol className="log-list">
      {logs.map((log, index) => (
        <li key={`${getLogMessage(log)}-${index}`}>
          {typeof log === "string" ? (
            <span>{log}</span>
          ) : (
            <>
              <div className="log-meta">
                {typeof log.timestamp === "string" ? <span>{log.timestamp}</span> : null}
                {typeof log.level === "string" ? <strong>{log.level}</strong> : null}
              </div>
              <span>{getLogMessage(log)}</span>
              {log.message ? null : <JsonBlock value={log} />}
            </>
          )}
        </li>
      ))}
    </ol>
  );
}
