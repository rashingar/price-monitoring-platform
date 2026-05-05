import { useCallback, useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ArtifactItem,
  BridgeArtifact,
  BridgeRunResponse,
  CsvRow,
  FileListItem,
  FileListResponse,
  FileRoot,
  ReadCsvFileResponse,
  SaveCsvResponse,
} from "../api/commerceTypes";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

const DEFAULT_MAX_ROWS = 1000;
const DEFAULT_STOCK_PATH = "C:\\Exports\\CheckWHouseBalance.csv";
const CSV_BRIDGE_STATE_KEY = "product-agent-ui:csv-bridge:v1";

interface CsvBridgePageState {
  selectedRoot: string;
  relativePath: string;
  lastOpenedFilePath: string;
  copyTargetPath: string;
  opencartExportPath: string;
  stockCsvPath: string;
  outputDir: string;
}

const initialCsvBridgePageState: CsvBridgePageState = {
  selectedRoot: "",
  relativePath: "",
  lastOpenedFilePath: "",
  copyTargetPath: "",
  opencartExportPath: "",
  stockCsvPath: "",
  outputDir: "",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatSize(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return `${value.toLocaleString()} bytes`;
}

function isCsvFile(item: FileListItem): boolean {
  return item.type === "file" && item.extension?.toLowerCase() === ".csv";
}

function getDisplayItems(items: FileListItem[]): FileListItem[] {
  return items
    .filter((item) => item.type === "directory" || isCsvFile(item))
    .sort((first, second) => {
      if (first.type !== second.type) {
        return first.type === "directory" ? -1 : 1;
      }

      return first.name.localeCompare(second.name);
    });
}

function joinRelativePath(relativePath: string, name: string): string {
  return relativePath.length > 0 ? `${relativePath}\\${name}` : name;
}

function getParentRelativePath(relativePath: string): string {
  const parts = relativePath.split(/[\\/]+/).filter(Boolean);
  parts.pop();
  return parts.join("\\");
}

function makeCopyPath(sourcePath: string): string {
  const dotIndex = sourcePath.lastIndexOf(".");
  if (dotIndex <= 0) {
    return `${sourcePath}_edited`;
  }

  return `${sourcePath.slice(0, dotIndex)}_edited${sourcePath.slice(dotIndex)}`;
}

function normalizeRowsForSave(columns: string[], rows: CsvRow[]): CsvRow[] {
  return rows.map((row) =>
    columns.reduce<CsvRow>((nextRow, column) => {
      nextRow[column] = row[column] ?? "";
      return nextRow;
    }, {}),
  );
}

function MetadataGrid({ csv }: { csv: ReadCsvFileResponse }) {
  return (
    <dl className="summary-grid csv-metadata-grid">
      <div>
        <dt>Filename</dt>
        <dd>{formatValue(csv.filename)}</dd>
      </div>
      <div>
        <dt>Path</dt>
        <dd>{formatValue(csv.path)}</dd>
      </div>
      <div>
        <dt>Delimiter</dt>
        <dd>{formatValue(csv.delimiter)}</dd>
      </div>
      <div>
        <dt>Encoding</dt>
        <dd>{formatValue(csv.encoding)}</dd>
      </div>
      <div>
        <dt>Returned rows</dt>
        <dd>{csv.returned_rows.toLocaleString()}</dd>
      </div>
      <div>
        <dt>Total rows</dt>
        <dd>{csv.total_rows.toLocaleString()}</dd>
      </div>
      <div>
        <dt>Size</dt>
        <dd>{formatSize(csv.size_bytes)}</dd>
      </div>
      <div>
        <dt>Modified</dt>
        <dd>{formatValue(csv.modified_at)}</dd>
      </div>
    </dl>
  );
}

function SaveResult({ title, result }: { title: string; result: SaveCsvResponse }) {
  return (
    <div className="state-block">
      <strong>{title}</strong>
      <dl className="summary-grid">
        <div>
          <dt>Path</dt>
          <dd>{formatValue(result.target_path ?? result.path)}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{formatValue(result.source_path)}</dd>
        </div>
        <div>
          <dt>Rows</dt>
          <dd>{formatValue(result.row_count ?? result.rows)}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatSize(result.size_bytes)}</dd>
        </div>
        <div>
          <dt>Modified</dt>
          <dd>{formatValue(result.modified_at)}</dd>
        </div>
      </dl>
    </div>
  );
}

function BridgeResult({ result }: { result: BridgeRunResponse }) {
  const summary = result.summary ?? {};
  const artifacts = Array.isArray(result.artifacts) ? result.artifacts : [];

  return (
    <div className="state-block">
      <strong>Bridge result</strong>
      <dl className="summary-grid">
        <div>
          <dt>Run ID</dt>
          <dd>{formatValue(result.run_id)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{formatValue(result.status)}</dd>
        </div>
        <div>
          <dt>Stock CSV</dt>
          <dd>{formatValue(result.stock_csv_path)}</dd>
        </div>
        <div>
          <dt>OpenCart export</dt>
          <dd>{formatValue(result.opencart_export_path)}</dd>
        </div>
        <div>
          <dt>Output dir</dt>
          <dd>{formatValue(result.output_dir)}</dd>
        </div>
      </dl>

      <div className="compact-list">
        <strong>Summary</strong>
        {Object.keys(summary).length > 0 ? (
          <dl className="summary-grid">
            {Object.entries(summary).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted">No summary counts returned.</p>
        )}
      </div>

      <div className="compact-list">
        <strong>Artifacts</strong>
        {artifacts.length > 0 ? (
          <ul>
            {artifacts.map((artifact, index) => (
              <li key={`${artifact.path ?? artifact.name ?? "artifact"}-${index}`}>
                <strong>{formatValue(artifact.name)}</strong>: {formatValue(artifact.path)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No artifact paths returned.</p>
        )}
      </div>
    </div>
  );
}

function getNameFromPath(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

function bridgeArtifactToItem(artifact: BridgeArtifact): ArtifactItem | null {
  if (!artifact.path) {
    return null;
  }

  const path = artifact.path;
  return {
    ...artifact,
    name: artifact.name || getNameFromPath(path),
    path,
    extension: artifact.extension ?? null,
    size_bytes: artifact.size_bytes ?? null,
    modified_at: artifact.modified_at ?? null,
    download_url: artifact.download_url ?? null,
    read_url: artifact.read_url ?? null,
    is_allowed: artifact.is_allowed === false ? false : true,
    can_read: artifact.can_read === false ? false : true,
    can_download: artifact.can_download === false ? false : true,
    warning: artifact.warning ?? null,
  };
}

function CsvBridgeSetupHint() {
  return (
    <div className="setup-hint compact">
      <strong>CSV/Bridge setup check</strong>
      <ul>
        <li>Commerce API must be running: <code>pricefetcher-api</code></li>
        <li>Safe roots are defined by the backend.</li>
        <li>Check <code>PRICEFETCHER_FILE_ROOTS</code> if expected folders are missing.</li>
      </ul>
    </div>
  );
}

export function CsvBridgePage() {
  const [persistedState, setPersistedState, resetPersistedState] =
    usePersistentPageState<CsvBridgePageState>(
      CSV_BRIDGE_STATE_KEY,
      initialCsvBridgePageState,
      { debounceMs: 250 },
    );
  const [roots, setRoots] = useState<FileRoot[]>([]);
  const [selectedRoot, setSelectedRoot] = useState(persistedState.selectedRoot);
  const [rootsError, setRootsError] = useState<string | null>(null);
  const [areRootsLoading, setAreRootsLoading] = useState(true);

  const [relativePath, setRelativePath] = useState(persistedState.relativePath);
  const [fileList, setFileList] = useState<FileListResponse | null>(null);
  const [fileListError, setFileListError] = useState<string | null>(null);
  const [isFileListLoading, setIsFileListLoading] = useState(false);

  const [csv, setCsv] = useState<ReadCsvFileResponse | null>(null);
  const [lastOpenedFilePath, setLastOpenedFilePath] = useState(persistedState.lastOpenedFilePath);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<CsvRow[]>([]);
  const [csvReadError, setCsvReadError] = useState<string | null>(null);
  const [isCsvReadLoading, setIsCsvReadLoading] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const [copyTargetPath, setCopyTargetPath] = useState(persistedState.copyTargetPath);
  const [saveCopyResult, setSaveCopyResult] = useState<SaveCsvResponse | null>(null);
  const [saveCopyError, setSaveCopyError] = useState<string | null>(null);
  const [isSaveCopyLoading, setIsSaveCopyLoading] = useState(false);

  const [confirmOverwritePath, setConfirmOverwritePath] = useState("");
  const [saveInPlaceResult, setSaveInPlaceResult] = useState<SaveCsvResponse | null>(null);
  const [saveInPlaceError, setSaveInPlaceError] = useState<string | null>(null);
  const [isSaveInPlaceLoading, setIsSaveInPlaceLoading] = useState(false);

  const [opencartExportPath, setOpencartExportPath] = useState(persistedState.opencartExportPath);
  const [stockCsvPath, setStockCsvPath] = useState(persistedState.stockCsvPath);
  const [outputDir, setOutputDir] = useState(persistedState.outputDir);
  const [bridgeResult, setBridgeResult] = useState<BridgeRunResponse | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [bridgeArtifactItems, setBridgeArtifactItems] = useState<ArtifactItem[]>([]);
  const [bridgeArtifactWarning, setBridgeArtifactWarning] = useState<string | null>(null);
  const [isBridgeLoading, setIsBridgeLoading] = useState(false);

  const displayItems = useMemo(
    () => getDisplayItems(fileList?.items ?? []),
    [fileList?.items],
  );

  const loadRoots = useCallback(async (signal?: AbortSignal) => {
    setAreRootsLoading(true);
    try {
      const nextRoots = await commerceClient.getFileRoots(signal);
      if (signal?.aborted) {
        return;
      }

      setRoots(nextRoots);
      setSelectedRoot((currentRoot) => currentRoot || nextRoots.find((root) => root.exists)?.path || "");
      setRootsError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setRootsError(getCommerceApiErrorMessage(error));
      }
    } finally {
      if (!signal?.aborted) {
        setAreRootsLoading(false);
      }
    }
  }, []);

  const loadFiles = useCallback(
    async (root: string, nextRelativePath: string, signal?: AbortSignal) => {
      if (!root) {
        setFileList(null);
        return;
      }

      setIsFileListLoading(true);
      try {
        const nextFileList = await commerceClient.listFiles(
          { root, relative_path: nextRelativePath || null },
          signal,
        );
        if (signal?.aborted) {
          return;
        }

        setFileList(nextFileList);
        setFileListError(null);
      } catch (error) {
        if (!signal?.aborted) {
          setFileListError(getCommerceApiErrorMessage(error));
        }
      } finally {
        if (!signal?.aborted) {
          setIsFileListLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadRoots(controller.signal);
    return () => controller.abort();
  }, [loadRoots]);

  useEffect(() => {
    const controller = new AbortController();
    void loadFiles(selectedRoot, relativePath, controller.signal);
    return () => controller.abort();
  }, [loadFiles, relativePath, selectedRoot]);

  useEffect(() => {
    setPersistedState({
      selectedRoot,
      relativePath,
      lastOpenedFilePath,
      copyTargetPath,
      opencartExportPath,
      stockCsvPath,
      outputDir,
    });
  }, [
    copyTargetPath,
    lastOpenedFilePath,
    opencartExportPath,
    outputDir,
    relativePath,
    selectedRoot,
    setPersistedState,
    stockCsvPath,
  ]);

  const openCsv = async (path: string) => {
    setIsCsvReadLoading(true);
    setCsvReadError(null);
    try {
      const nextCsv = await commerceClient.readCsvFile({
        path,
        delimiter: null,
        max_rows: DEFAULT_MAX_ROWS,
      });
      setCsv(nextCsv);
      setLastOpenedFilePath(nextCsv.path || path);
      setColumns(nextCsv.columns);
      setRows(nextCsv.rows);
      setCopyTargetPath(makeCopyPath(nextCsv.path || path));
      setConfirmOverwritePath("");
      setSaveCopyResult(null);
      setSaveInPlaceResult(null);
      setIsDirty(false);
      if (!opencartExportPath) {
        setOpencartExportPath(nextCsv.path || path);
      }
    } catch (error) {
      setCsvReadError(getCommerceApiErrorMessage(error));
    } finally {
      setIsCsvReadLoading(false);
    }
  };

  const updateCell = (rowIndex: number, column: string, value: string) => {
    setRows((currentRows) =>
      currentRows.map((row, index) => (index === rowIndex ? { ...row, [column]: value } : row)),
    );
    setIsDirty(true);
  };

  const addRow = () => {
    setRows((currentRows) => [
      ...currentRows,
      columns.reduce<CsvRow>((nextRow, column) => {
        nextRow[column] = "";
        return nextRow;
      }, {}),
    ]);
    setIsDirty(true);
  };

  const deleteRow = (rowIndex: number) => {
    setRows((currentRows) => currentRows.filter((_, index) => index !== rowIndex));
    setIsDirty(true);
  };

  const saveCopy = async () => {
    if (!csv) {
      return;
    }

    setIsSaveCopyLoading(true);
    setSaveCopyError(null);
    setSaveCopyResult(null);
    try {
      const result = await commerceClient.saveCsvCopy({
        source_path: csv.path,
        target_path: copyTargetPath.trim(),
        columns,
        rows: normalizeRowsForSave(columns, rows),
        delimiter: csv.delimiter,
      });
      setSaveCopyResult(result);
      setIsDirty(false);
    } catch (error) {
      setSaveCopyError(getCommerceApiErrorMessage(error));
    } finally {
      setIsSaveCopyLoading(false);
    }
  };

  const saveInPlace = async () => {
    if (!csv || confirmOverwritePath !== csv.path) {
      return;
    }

    setIsSaveInPlaceLoading(true);
    setSaveInPlaceError(null);
    setSaveInPlaceResult(null);
    try {
      const result = await commerceClient.saveCsvFile({
        path: csv.path,
        columns,
        rows: normalizeRowsForSave(columns, rows),
        delimiter: csv.delimiter,
      });
      setSaveInPlaceResult(result);
      setIsDirty(false);
      setConfirmOverwritePath("");
    } catch (error) {
      setSaveInPlaceError(getCommerceApiErrorMessage(error));
    } finally {
      setIsSaveInPlaceLoading(false);
    }
  };

  const runBridge = async () => {
    setIsBridgeLoading(true);
    setBridgeError(null);
    setBridgeResult(null);
    setBridgeArtifactItems([]);
    setBridgeArtifactWarning(null);
    try {
      const result = await commerceClient.runBridge({
        opencart_export_path: opencartExportPath.trim(),
        stock_csv_path: stockCsvPath.trim() || null,
        output_dir: outputDir.trim() || null,
      });
      setBridgeResult(result);
      const responseArtifacts = (result.artifacts ?? [])
        .map(bridgeArtifactToItem)
        .filter((item): item is ArtifactItem => item !== null);
      setBridgeArtifactItems(responseArtifacts);

      const runId = result.run_id === null || result.run_id === undefined ? "" : String(result.run_id);
      if (runId) {
        try {
          const artifactList = await commerceClient.listBridgeRunArtifacts(runId);
          setBridgeArtifactItems(artifactList.items.length > 0 ? artifactList.items : responseArtifacts);
        } catch (artifactError) {
          setBridgeArtifactWarning(
            `Bridge finished, but artifact listing failed: ${getCommerceApiErrorMessage(artifactError)}`,
          );
        }
      }
    } catch (error) {
      setBridgeError(getCommerceApiErrorMessage(error));
    } finally {
      setIsBridgeLoading(false);
    }
  };

  const previewArtifact = async (path: string) => {
    const response = await commerceClient.readArtifact(path, 200_000);
    return response.content;
  };

  const canSaveCopy = Boolean(csv && copyTargetPath.trim().length > 0 && !isSaveCopyLoading);
  const canSaveInPlace = Boolean(
    csv && confirmOverwritePath === csv.path && !isSaveInPlaceLoading,
  );
  const canRunBridge = opencartExportPath.trim().length > 0 && !isBridgeLoading;

  const resetSavedCsvBridgeState = () => {
    resetPersistedState();
    setSelectedRoot(initialCsvBridgePageState.selectedRoot);
    setRelativePath(initialCsvBridgePageState.relativePath);
    setLastOpenedFilePath(initialCsvBridgePageState.lastOpenedFilePath);
    setCopyTargetPath(initialCsvBridgePageState.copyTargetPath);
    setOpencartExportPath(initialCsvBridgePageState.opencartExportPath);
    setStockCsvPath(initialCsvBridgePageState.stockCsvPath);
    setOutputDir(initialCsvBridgePageState.outputDir);
  };

  return (
    <div className="page-stack csv-bridge-page">
      <section className="page-header">
        <p className="eyebrow">CSV/Bridge</p>
        <h2>CSV bridge workspace</h2>
        <p>Browse backend-approved roots, edit CSV rows as strings, and run the bridge.</p>
        <button className="text-button" type="button" onClick={resetSavedCsvBridgeState}>
          Reset saved CSV/Bridge state
        </button>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CSV viewer/editor</p>
            <h3>Safe file browser</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadRoots()}>
            Refresh roots
          </button>
        </div>

        {areRootsLoading ? <LoadingState label="Loading safe roots..." /> : null}
        {rootsError ? (
          <>
            <ErrorState message={rootsError} onRetry={() => void loadRoots()} />
            <CsvBridgeSetupHint />
          </>
        ) : null}
        {!areRootsLoading && !rootsError && roots.length === 0 ? (
          <EmptyState title="No safe roots found" message="The commerce backend returned no roots." />
        ) : null}

        {roots.length > 0 ? (
          <div className="browser-layout">
            <aside className="browser-panel">
              <label>
                Safe root
                <select
                  value={selectedRoot}
                  onChange={(event) => {
                    setSelectedRoot(event.target.value);
                    setRelativePath("");
                    setFileList(null);
                  }}
                >
                  {roots.map((root) => (
                    <option key={root.path} value={root.path} disabled={!root.exists}>
                      {root.path}
                      {root.exists ? "" : " (missing)"}
                    </option>
                  ))}
                </select>
              </label>

              <div className="path-bar">
                <span className="muted">Folder</span>
                <strong>{relativePath || "\\"}</strong>
              </div>

              <div className="button-row">
                <button
                  className="button secondary"
                  type="button"
                  disabled={!relativePath}
                  onClick={() => setRelativePath((currentPath) => getParentRelativePath(currentPath))}
                >
                  Up
                </button>
                <button
                  className="button secondary"
                  type="button"
                  disabled={!selectedRoot || isFileListLoading}
                  onClick={() => void loadFiles(selectedRoot, relativePath)}
                >
                  Refresh files
                </button>
              </div>

              {isFileListLoading ? <LoadingState label="Loading files..." /> : null}
              {fileListError ? (
                <>
                  <ErrorState
                    message={fileListError}
                    onRetry={() => void loadFiles(selectedRoot, relativePath)}
                  />
                  <CsvBridgeSetupHint />
                </>
              ) : null}

              {!isFileListLoading && !fileListError && displayItems.length === 0 ? (
                <EmptyState
                  title="No CSV files found"
                  message="Only directories and .csv files are shown."
                />
              ) : null}

              {displayItems.length > 0 ? (
                <ul className="file-list">
                  {displayItems.map((item) => (
                    <li key={item.path}>
                      <button
                        className="file-list-button"
                        type="button"
                        onClick={() => {
                          if (item.type === "directory") {
                            setRelativePath(joinRelativePath(fileList?.relative_path ?? relativePath, item.name));
                          } else {
                            void openCsv(item.path);
                          }
                        }}
                      >
                        <span>{item.type === "directory" ? "Folder" : "CSV"}</span>
                        <strong>{item.name}</strong>
                        <small>
                          {item.type === "directory"
                            ? formatValue(item.modified_at)
                            : `${formatSize(item.size_bytes)} | ${formatValue(item.modified_at)}`}
                        </small>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </aside>

            <div className="editor-panel">
              {isCsvReadLoading ? <LoadingState label="Reading CSV..." /> : null}
              {csvReadError ? (
                <>
                  <ErrorState message={csvReadError} />
                  <CsvBridgeSetupHint />
                </>
              ) : null}
              {!csv && !isCsvReadLoading && !csvReadError ? (
                <EmptyState title="No CSV open" message="Choose a CSV from the safe file browser." />
              ) : null}

              {csv ? (
                <div className="page-stack">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Open CSV</p>
                      <h3>{csv.filename || "CSV file"}</h3>
                    </div>
                    <span className={`status-badge ${isDirty ? "queued" : "success"}`}>
                      {isDirty ? "Edited" : "Saved state"}
                    </span>
                  </div>

                  <MetadataGrid csv={csv} />

                  <div className="toolbar">
                    <p className="muted">
                      Editing {rows.length.toLocaleString()} returned rows across{" "}
                      {columns.length.toLocaleString()} columns.
                    </p>
                    <button
                      className="button secondary"
                      type="button"
                      disabled={columns.length === 0}
                      onClick={addRow}
                    >
                      Add row
                    </button>
                  </div>

                  {columns.length === 0 ? (
                    <EmptyState title="No columns returned" message="This CSV has no editable columns." />
                  ) : (
                    <div className="table-wrap csv-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Row</th>
                            {columns.map((column) => (
                              <th key={column}>{column}</th>
                            ))}
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, rowIndex) => (
                            <tr key={rowIndex}>
                              <td className="nowrap-cell">{rowIndex + 1}</td>
                              {columns.map((column) => (
                                <td key={column}>
                                  <input
                                    className="table-input"
                                    value={row[column] ?? ""}
                                    onChange={(event) =>
                                      updateCell(rowIndex, column, event.target.value)
                                    }
                                  />
                                </td>
                              ))}
                              <td>
                                <button
                                  className="button secondary"
                                  type="button"
                                  onClick={() => deleteRow(rowIndex)}
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="save-grid">
                    <div className="save-box">
                      <div>
                        <p className="eyebrow">Safe save</p>
                        <h4>Save copy</h4>
                      </div>
                      <label>
                        Target path
                        <input
                          value={copyTargetPath}
                          onChange={(event) => setCopyTargetPath(event.target.value)}
                        />
                      </label>
                      <button
                        className="button primary inline-button"
                        type="button"
                        disabled={!canSaveCopy}
                        onClick={() => void saveCopy()}
                      >
                        {isSaveCopyLoading ? "Saving copy..." : "Save copy"}
                      </button>
                      {saveCopyError ? <ErrorState message={saveCopyError} /> : null}
                      {saveCopyResult ? <SaveResult title="Copy saved" result={saveCopyResult} /> : null}
                    </div>

                    <div className="save-box">
                      <div>
                        <p className="eyebrow">Overwrite</p>
                        <h4>Save in place</h4>
                      </div>
                      <p className="muted">
                        Type the exact path to confirm overwrite: {csv.path}
                      </p>
                      <label>
                        Confirmation path
                        <input
                          value={confirmOverwritePath}
                          onChange={(event) => setConfirmOverwritePath(event.target.value)}
                        />
                      </label>
                      <button
                        className="button secondary inline-button"
                        type="button"
                        disabled={!canSaveInPlace}
                        onClick={() => void saveInPlace()}
                      >
                        {isSaveInPlaceLoading ? "Saving in place..." : "Save in place"}
                      </button>
                      {saveInPlaceError ? <ErrorState message={saveInPlaceError} /> : null}
                      {saveInPlaceResult ? (
                        <SaveResult title="File overwritten" result={saveInPlaceResult} />
                      ) : null}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Bridge runner</p>
            <h3>Execute CSV bridge</h3>
          </div>
        </div>

        <div className="form">
          <label>
            OpenCart export path
            <input
              value={opencartExportPath}
              onChange={(event) => setOpencartExportPath(event.target.value)}
              placeholder="C:\\Exports\\export_2026-04-28.csv"
            />
          </label>
          <label>
            Stock CSV path
            <input
              value={stockCsvPath}
              onChange={(event) => setStockCsvPath(event.target.value)}
              placeholder={DEFAULT_STOCK_PATH}
            />
          </label>
          <label>
            Output directory
            <input
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              placeholder="Leave empty for backend default"
            />
          </label>
          <p className="muted">
            Default stock CSV is {DEFAULT_STOCK_PATH}. Stock CSV schema is model,quantity.
            Composite/bundle models are ignored by the backend.
          </p>
          <button
            className="button primary inline-button"
            type="button"
            disabled={!canRunBridge}
            onClick={() => void runBridge()}
          >
            {isBridgeLoading ? "Running bridge..." : "Run Bridge"}
          </button>
        </div>

        {bridgeError ? <ErrorState message={bridgeError} /> : null}
        {bridgeResult ? <BridgeResult result={bridgeResult} /> : null}
        {bridgeArtifactWarning ? <p className="state-block">{bridgeArtifactWarning}</p> : null}
        {bridgeArtifactItems.length > 0 ? (
          <ArtifactList
            title="Bridge run artifacts"
            items={bridgeArtifactItems}
            onPreview={previewArtifact}
            getDownloadUrl={commerceClient.getArtifactDownloadUrl}
          />
        ) : null}
      </section>
    </div>
  );
}
