      const { useEffect, useMemo, useRef, useState } = React;
      const NUMERIC_RE = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;

      const deepClone = (value) => JSON.parse(JSON.stringify(value));

      const mergeOrder = (configuredOrder, columns) => {
        const order = [];
        const seen = new Set();
        for (const item of configuredOrder || []) {
          if (!seen.has(item)) {
            order.push(item);
            seen.add(item);
          }
        }
        for (const item of columns || []) {
          if (!seen.has(item)) {
            order.push(item);
            seen.add(item);
          }
        }
        return order;
      };

      const toNumericValue = (value) => {
        if (typeof value === "boolean") {
          return null;
        }
        if (typeof value === "number") {
          return Number.isNaN(value) ? null : value;
        }
        if (typeof value === "string") {
          const text = value.trim();
          if (NUMERIC_RE.test(text)) {
            const parsed = Number(text);
            return Number.isNaN(parsed) ? null : parsed;
          }
        }
        return null;
      };

      const sortableValue = (value) => {
        const numeric = toNumericValue(value);
        if (numeric !== null) {
          return { rank: 0, value: numeric };
        }
        if (value === null || value === undefined) {
          return { rank: 2, value: "" };
        }
        return { rank: 1, value: String(value) };
      };

      function App() {
        const [meta, setMeta] = useState({ root: "", view_name: "" });
        const [view, setView] = useState(null);
        const viewRef = useRef(null);
        const [scan, setScan] = useState({ rows: [], columns: { all: [], visible: [], alias: {} }, summary: null, warnings: [] });
        const [draggingColumn, setDraggingColumn] = useState(null);
        const [dragOverColumn, setDragOverColumn] = useState(null);
        const [draggingPinnedId, setDraggingPinnedId] = useState(null);
        const [dragOverPinnedId, setDragOverPinnedId] = useState(null);
        const [loading, setLoading] = useState(true);
        const [saving, setSaving] = useState(false);
        const [dirty, setDirty] = useState(false);
        const [error, setError] = useState("");
        const [message, setMessage] = useState("");

        useEffect(() => {
          const handler = (event) => {
            if (!dirty) {
              return;
            }
            event.preventDefault();
            event.returnValue = "";
          };
          window.addEventListener("beforeunload", handler);
          return () => window.removeEventListener("beforeunload", handler);
        }, [dirty]);

        useEffect(() => {
          loadInitial();
        }, []);

        useEffect(() => {
          viewRef.current = view;
        }, [view]);

        const allColumns = useMemo(() => {
          if (!view) {
            return [];
          }
          const fromScan = scan.columns?.all || [];
          const fromComputed = (view.columns?.computed || []).map((item) => item.name).filter(Boolean);
          return mergeOrder(mergeOrder(view.columns?.order || [], fromScan), fromComputed);
        }, [scan.columns, view]);

        const visibleColumns = useMemo(() => {
          if (!view) {
            return [];
          }
          const hidden = new Set(view.columns.hidden || []);
          return allColumns.filter((column) => !hidden.has(column));
        }, [allColumns, view]);

        const displayRows = useMemo(() => {
          if (!view) {
            return [];
          }

          const inputRows = Array.isArray(scan.rows) ? scan.rows : [];
          const pinnedIds = view.rows?.pinned_ids || [];
          const pinnedIndex = new Map(pinnedIds.map((path, index) => [path, index]));
          const pinnedRows = [];
          const otherRows = [];

          for (const row of inputRows) {
            const path = row.path;
            if (typeof path === "string" && pinnedIndex.has(path)) {
              pinnedRows.push(row);
            } else {
              otherRows.push(row);
            }
          }

          pinnedRows.sort((a, b) => pinnedIndex.get(a.path) - pinnedIndex.get(b.path));

          const sortBy = view.rows?.sort?.by;
          const direction = view.rows?.sort?.direction === "desc" ? -1 : 1;
          if (sortBy) {
            otherRows.sort((a, b) => {
              const left = sortableValue(a[sortBy]);
              const right = sortableValue(b[sortBy]);
              if (left.rank !== right.rank) {
                return left.rank - right.rank;
              }
              if (typeof left.value === "number" && typeof right.value === "number") {
                return (left.value - right.value) * direction;
              }
              return left.value.localeCompare(right.value) * direction;
            });
          }

          return [...pinnedRows, ...otherRows];
        }, [scan.rows, view]);

        async function loadInitial() {
          setLoading(true);
          setError("");
          setMessage("");
          try {
            const metaResp = await fetch("/api/meta");
            if (!metaResp.ok) {
              throw new Error(await metaResp.text());
            }
            const metaPayload = await metaResp.json();
            setMeta(metaPayload);

            const viewResp = await fetch("/api/view");
            if (!viewResp.ok) {
              throw new Error(await viewResp.text());
            }
            const viewPayload = await viewResp.json();
            setView(viewPayload);
            viewRef.current = viewPayload;

            await runScan(viewPayload);
            setDirty(false);
          } catch (err) {
            setError(String(err));
          } finally {
            setLoading(false);
          }
        }

        async function runScan(activeView = view) {
          if (!activeView) {
            return;
          }
          setMessage("");
          setError("");
          const resp = await fetch("/api/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ view: activeView }),
          });
          if (!resp.ok) {
            throw new Error(await resp.text());
          }
          const payload = await resp.json();
          setScan(payload);
        }

        async function refresh() {
          setLoading(true);
          try {
            await runScan(view);
          } catch (err) {
            setError(String(err));
          } finally {
            setLoading(false);
          }
        }

        async function save() {
          const activeView = viewRef.current;
          if (!activeView) {
            return;
          }
          setSaving(true);
          setMessage("");
          setError("");
          try {
            const resp = await fetch("/api/view", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(activeView),
            });
            if (!resp.ok) {
              throw new Error(await resp.text());
            }
            const saved = await resp.json();
            setView(saved);
            viewRef.current = saved;
            setDirty(false);
            setMessage("View saved.");
            await runScan(saved);
          } catch (err) {
            setError(String(err));
          } finally {
            setSaving(false);
          }
        }

        function mutateView(mutator) {
          const current = viewRef.current;
          if (!current) {
            return;
          }
          const next = deepClone(current);
          mutator(next);
          viewRef.current = next;
          setView(next);
          setDirty(true);
          setMessage("");
        }

        function reorderColumns(draggedColumn, targetColumn) {
          if (!draggedColumn || !targetColumn || draggedColumn === targetColumn) {
            return;
          }

          const fromIndex = allColumns.indexOf(draggedColumn);
          const toIndex = allColumns.indexOf(targetColumn);
          if (fromIndex < 0 || toIndex < 0) {
            return;
          }

          const nextOrder = [...allColumns];
          const [item] = nextOrder.splice(fromIndex, 1);
          nextOrder.splice(toIndex, 0, item);
          mutateView((draft) => {
            draft.columns.order = nextOrder;
          });
        }

        function toggleHidden(columnName) {
          mutateView((draft) => {
            const set = new Set(draft.columns.hidden || []);
            if (set.has(columnName)) {
              set.delete(columnName);
            } else {
              set.add(columnName);
            }
            draft.columns.hidden = Array.from(set);
          });
        }

        function setAlias(columnName, aliasValue) {
          mutateView((draft) => {
            if (!aliasValue.trim()) {
              delete draft.columns.alias[columnName];
              return;
            }
            draft.columns.alias[columnName] = aliasValue;
          });
        }

        function setAllVisibility(visible) {
          mutateView((draft) => {
            draft.columns.hidden = visible ? [] : [...allColumns];
          });
        }

        function addComputed() {
          mutateView((draft) => {
            draft.columns.computed.push({ name: "", expr: "" });
          });
        }

        function removeComputed(index) {
          mutateView((draft) => {
            draft.columns.computed.splice(index, 1);
          });
        }

        function updateComputed(index, field, value) {
          mutateView((draft) => {
            draft.columns.computed[index][field] = value;
          });
        }

        function onColumnDragStart(event, column) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", column);
          setDraggingColumn(column);
        }

        function onColumnDrop(event, targetColumn) {
          event.preventDefault();
          const draggedFromData = event.dataTransfer.getData("text/plain");
          reorderColumns(draggedFromData || draggingColumn, targetColumn);
          setDraggingColumn(null);
          setDragOverColumn(null);
        }

        function togglePin(path) {
          if (!path) {
            return;
          }

          mutateView((draft) => {
            const pinnedIds = [...(draft.rows.pinned_ids || [])];
            const index = pinnedIds.indexOf(path);
            if (index >= 0) {
              pinnedIds.splice(index, 1);
            } else {
              pinnedIds.push(path);
            }
            draft.rows.pinned_ids = pinnedIds;
          });
        }

        function reorderPinnedRows(draggedPath, targetPath) {
          if (!draggedPath || !targetPath || draggedPath === targetPath) {
            return;
          }

          mutateView((draft) => {
            const pinnedIds = [...(draft.rows.pinned_ids || [])];
            const fromIndex = pinnedIds.indexOf(draggedPath);
            const toIndex = pinnedIds.indexOf(targetPath);
            if (fromIndex < 0 || toIndex < 0) {
              return;
            }
            const [item] = pinnedIds.splice(fromIndex, 1);
            pinnedIds.splice(toIndex, 0, item);
            draft.rows.pinned_ids = pinnedIds;
          });
        }

        function toggleSortByColumn(column) {
          mutateView((draft) => {
            if (draft.rows.sort.by === column) {
              draft.rows.sort.direction = draft.rows.sort.direction === "asc" ? "desc" : "asc";
              return;
            }
            draft.rows.sort.by = column;
            draft.rows.sort.direction = "asc";
          });
        }

        function sortIndicatorFor(column) {
          const sortBy = view.rows?.sort?.by;
          const direction = view.rows?.sort?.direction || "asc";
          if (sortBy !== column) {
            return "↕";
          }
          return direction === "desc" ? "▼" : "▲";
        }

        if (loading && !view) {
          return <div className="app"><div className="panel">Loading...</div></div>;
        }

        if (!view) {
          return <div className="app"><div className="panel error">{error || "Failed to load view."}</div></div>;
        }

        return (
          <div className="app">
            <div className="panel toolbar">
              <div>
                <div><strong>EasyLogger</strong></div>
                <div className="meta">Root: {meta.root}</div>
                <div className="meta">View: {meta.view_name}</div>
              </div>
              <div className="actions">
                <button onClick={refresh} disabled={loading}>Refresh</button>
                <button className="primary" onClick={save} disabled={saving}>Save View</button>
              </div>
            </div>

            <div className="panel">
              <div className="status">
                {scan.summary
                  ? `files=${scan.summary.total_files}, matched=${scan.summary.matched_files}, records=${scan.summary.parsed_records}, warnings=${scan.summary.warning_count}`
                  : "No scan summary."}
                {dirty ? <span className="dirty">  |  Unsaved changes</span> : null}
              </div>
              {message ? <div className="status">{message}</div> : null}
              {error ? <div className="error">{error}</div> : null}
              {scan.warnings?.length ? (
                <>
                  <div className="hint">Scan warnings:</div>
                  <ul className="warning-list">
                    {scan.warnings.slice(0, 20).map((item, idx) => (
                      <li key={`${item.path}-${idx}`}>{item.path}: {item.message}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>

            <div className="grid-two">
              <div className="panel">
                <h3 className="section-title">Columns</h3>
                <div className="column-tools">
                  <button type="button" onClick={() => setAllVisibility(true)}>All visible</button>
                  <button type="button" onClick={() => setAllVisibility(false)}>All invisible</button>
                </div>
                <div className="column-grid-head hint">
                  <span>#</span>
                  <span>Column</span>
                  <span>Alias</span>
                  <span>Visible</span>
                </div>
                {allColumns.map((column) => (
                  <div
                    className={`column-row ${dragOverColumn === column ? "drag-over" : ""}`}
                    key={column}
                    onDragOver={(event) => {
                      event.preventDefault();
                      if (column !== draggingColumn) {
                        setDragOverColumn(column);
                      }
                    }}
                    onDragLeave={() => {
                      if (dragOverColumn === column) {
                        setDragOverColumn(null);
                      }
                    }}
                    onDrop={(event) => onColumnDrop(event, column)}
                  >
                    <span
                      className="drag-handle"
                      title="Drag to reorder"
                      draggable
                      onDragStart={(event) => onColumnDragStart(event, column)}
                      onDragEnd={() => {
                        setDraggingColumn(null);
                        setDragOverColumn(null);
                      }}
                    >
                      ⋮⋮
                    </span>
                    <span className="column-name">{column}</span>
                    <input
                      value={view.columns.alias[column] || ""}
                      placeholder="alias"
                      onChange={(event) => setAlias(column, event.target.value)}
                    />
                    <label className="column-visibility">
                      <input
                        type="checkbox"
                        checked={!view.columns.hidden.includes(column)}
                        onChange={() => toggleHidden(column)}
                      />
                      visible
                    </label>
                  </div>
                ))}

                <h3 className="section-title">Computed Columns</h3>
                {(view.columns.computed || []).map((item, index) => (
                  <div className="computed-row" key={`computed-${index}`}>
                    <input
                      value={item.name}
                      placeholder="name"
                      onChange={(event) => updateComputed(index, "name", event.target.value)}
                    />
                    <input
                      value={item.expr}
                      placeholder='row["loss"] * row["step"]'
                      onChange={(event) => updateComputed(index, "expr", event.target.value)}
                    />
                    <button type="button" onClick={() => removeComputed(index)}>Delete</button>
                  </div>
                ))}
                <button type="button" onClick={addComputed}>Add computed column</button>
              </div>

              <div className="panel">
                <h3 className="section-title">Data</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th className="row-controls">Row</th>
                        {visibleColumns.map((column) => (
                          <th
                            className="sortable"
                            key={`head-${column}`}
                            onClick={() => toggleSortByColumn(column)}
                            title="Click to toggle asc/desc sort"
                          >
                            {view.columns.alias[column] || column}
                            <span className="sort-indicator">{sortIndicatorFor(column)}</span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {displayRows.map((row) => {
                        const rowPath = typeof row.path === "string" ? row.path : "";
                        const isPinned = (view.rows?.pinned_ids || []).includes(rowPath);
                        return (
                        <tr
                          className={`${isPinned ? "pinned-row" : ""} ${dragOverPinnedId === rowPath ? "pinned-drop-target" : ""}`}
                          key={row.path}
                          onDragOver={(event) => {
                            if (!draggingPinnedId || !isPinned || rowPath === draggingPinnedId) {
                              return;
                            }
                            event.preventDefault();
                            setDragOverPinnedId(rowPath);
                          }}
                          onDragLeave={() => {
                            if (dragOverPinnedId === rowPath) {
                              setDragOverPinnedId(null);
                            }
                          }}
                          onDrop={(event) => {
                            if (!draggingPinnedId || !isPinned) {
                              return;
                            }
                            event.preventDefault();
                            reorderPinnedRows(draggingPinnedId, rowPath);
                            setDraggingPinnedId(null);
                            setDragOverPinnedId(null);
                          }}
                        >
                          <td className="row-controls">
                            <div className="row-control-wrap">
                              <button
                                className={`pin-toggle ${isPinned ? "pinned" : ""}`}
                                onClick={() => togglePin(rowPath)}
                                type="button"
                                title={isPinned ? "Unpin row" : "Pin row to top"}
                              >
                                {isPinned ? "Pinned" : "Pin"}
                              </button>
                              {isPinned ? (
                                <span
                                  className="row-drag-handle"
                                  draggable
                                  title="Drag to reorder pinned rows"
                                  onDragStart={(event) => {
                                    event.dataTransfer.effectAllowed = "move";
                                    event.dataTransfer.setData("text/plain", rowPath);
                                    setDraggingPinnedId(rowPath);
                                  }}
                                  onDragEnd={() => {
                                    setDraggingPinnedId(null);
                                    setDragOverPinnedId(null);
                                  }}
                                >
                                  ⋮⋮
                                </span>
                              ) : null}
                            </div>
                          </td>
                          {visibleColumns.map((column) => {
                            const value = row[column];
                            const text = value === null || value === undefined ? "null" : String(value);
                            return <td key={`${row.path}-${column}`}>{text}</td>;
                          })}
                        </tr>
                        );
                      })}
                      {!displayRows.length ? (
                        <tr>
                          <td colSpan={Math.max(visibleColumns.length + 1, 1)}>No data. Click Refresh after adding log files.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        );
      }

      ReactDOM.createRoot(document.getElementById("root")).render(<App />);
