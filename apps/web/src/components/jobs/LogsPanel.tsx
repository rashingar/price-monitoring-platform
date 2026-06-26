import type { LogEntry } from "../../api/types";
import { EmptyState } from "../layout/StateBlocks";
import { JsonBlock } from "./JsonBlock";

interface LogsPanelProps {
  logs: LogEntry[];
}

export function getLogMessage(log: LogEntry): string {
  if (typeof log === "string") {
    return log;
  }

  if (typeof log.message === "string") {
    return log.message;
  }

  return JSON.stringify(log) ?? "Log entry";
}

export function formatLogsForCopy(logs: LogEntry[]): string {
  return logs
    .map((log) => {
      if (typeof log === "string") {
        return log;
      }

      const parts = [
        typeof log.timestamp === "string" ? log.timestamp : null,
        typeof log.level === "string" ? log.level.toUpperCase() : null,
        getLogMessage(log),
      ].filter((part): part is string => Boolean(part));
      return parts.join(" ");
    })
    .join("\n");
}

export function LogsPanel({ logs }: LogsPanelProps) {
  if (logs.length === 0) {
    return <EmptyState title="No logs yet" message="No log entries have been stored for this job." />;
  }

  return (
    <ol className="log-list" aria-label="Job logs">
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
