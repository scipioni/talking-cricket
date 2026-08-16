import { useEffect, useState, useRef } from "react";
import {
  Activity,
  Bot,
  User,
  Brain,
  Download,
  Search,
  Code,
  AlertTriangle,
  CheckCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
} from "lucide-react";

// Types representing our telemetry telemetry events
interface TelemetryEvent {
  type: "incoming_update" | "outgoing_response" | "llm_transaction";
  chat_id: number;
  timestamp: string;
  [key: string]: any;
}

interface ActiveSession {
  chat_id: number;
  last_active: string;
  event_count: number;
}

export default function App() {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<number | null>(null);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedLlmCalls, setExpandedLlmCalls] = useState<Record<string, boolean>>({});

  const eventsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch session list on mount
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && activeChatId === null) {
          selectSession(data[0].chat_id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch sessions list:", err);
    }
  };

  const selectSession = async (chatId: number) => {
    setActiveChatId(chatId);
    try {
      const res = await fetch(`/api/sessions/${chatId}/events`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      } else {
        setEvents([]);
      }
    } catch (err) {
      console.error(`Failed to fetch events for chat_id=${chatId}:`, err);
      setEvents([]);
    }
  };

  // Setup WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8080";
    const wsUrl = `${protocol}//${host}/telemetry/ws`;

    const connectWs = () => {
      console.log("Connecting to telemetry WebSocket:", wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        console.log("Telemetry WebSocket connected.");
      };

      ws.onclose = () => {
        setConnected(false);
        console.log("Telemetry WebSocket disconnected. Retrying in 3s...");
        setTimeout(connectWs, 3000);
      };

      ws.onmessage = (messageEvent) => {
        try {
          const event: TelemetryEvent = JSON.parse(messageEvent.data);
          const eventChatId = event.chat_id;

          // 1. If it matches current session, append to view
          setEvents((prev) => {
            if (activeChatId === eventChatId) {
              return [...prev, event];
            }
            return prev;
          });

          // 2. Update active sessions list
          setSessions((prevSessions) => {
            const exists = prevSessions.some((s) => s.chat_id === eventChatId);
            let updated: ActiveSession[];

            if (exists) {
              updated = prevSessions.map((s) => {
                if (s.chat_id === eventChatId) {
                  return {
                    ...s,
                    event_count: s.event_count + 1,
                    last_active: event.timestamp,
                  };
                }
                return s;
              });
            } else {
              updated = [
                {
                  chat_id: eventChatId,
                  last_active: event.timestamp,
                  event_count: 1,
                },
                ...prevSessions,
              ];
            }

            // Sort by recency
            return updated.sort(
              (a, b) => new Date(b.last_active).getTime() - new Date(a.last_active).getTime()
            );
          });
        } catch (err) {
          console.error("Error parsing WS telemetry message:", err);
        }
      };
    };

    connectWs();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [activeChatId]);

  // Scroll to bottom on new events
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const toggleLlmExpand = (eventId: string) => {
    setExpandedLlmCalls((prev) => ({
      ...prev,
      [eventId]: !prev[eventId],
    }));
  };

  const filteredSessions = sessions.filter((s) =>
    s.chat_id.toString().includes(searchTerm)
  );

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return "";
    }
  };

  const formatFullDate = (isoString: string) => {
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  };

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* 1. SIDEBAR */}
      <div className="w-80 border-r border-slate-800 bg-slate-900 flex flex-col h-full shrink-0">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-indigo-400 animate-pulse" />
            <h1 className="font-bold text-lg tracking-wide text-slate-50">Calobot Monitor</h1>
          </div>
          <div className="flex items-center gap-1.5 bg-slate-950/50 px-2.5 py-1 rounded-full text-xs">
            <span
              className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`}
            />
            <span className="text-slate-400 font-medium">
              {connected ? "Live" : "Offline"}
            </span>
          </div>
        </div>

        {/* Sidebar Search */}
        <div className="p-3 border-b border-slate-800/80">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search chat_id..."
              className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filteredSessions.length === 0 ? (
            <div className="text-center py-8 text-slate-500 text-sm">
              No sessions found
            </div>
          ) : (
            filteredSessions.map((session) => {
              const isActive = session.chat_id === activeChatId;
              return (
                <button
                  key={session.chat_id}
                  onClick={() => selectSession(session.chat_id)}
                  className={`w-full text-left p-3 rounded-lg flex flex-col gap-1 transition-all ${
                    isActive
                      ? "bg-indigo-650/40 border border-indigo-500/55 shadow-md shadow-indigo-950"
                      : "hover:bg-slate-800 border border-transparent"
                  }`}
                >
                  <div className="flex justify-between items-center w-full">
                    <span className="font-semibold text-sm text-slate-200">
                      ID: {session.chat_id}
                    </span>
                    <span className="text-xxs text-slate-400 font-mono">
                      {formatTime(session.last_active)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {session.event_count} telemetry traces
                    </span>
                  </div>
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* 2. CHAT STREAM / MAIN WINDOW */}
      <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
        {activeChatId ? (
          <>
            {/* Main Window Header */}
            <div className="h-16 border-b border-slate-800 bg-slate-900/60 px-6 flex items-center justify-between shrink-0">
              <div>
                <h2 className="font-bold text-slate-100">Session Trace #{activeChatId}</h2>
                <p className="text-xs text-slate-400">
                  Causal timeline trace of the user conversation and model completions
                </p>
              </div>
              <a
                href={`/api/export/${activeChatId}`}
                download={`session_${activeChatId}_activity.json`}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 transition-colors text-white px-3.5 py-1.5 rounded-lg text-sm font-semibold shadow-md cursor-pointer"
              >
                <Download className="h-4 w-4" />
                Export Activity JSON
              </a>
            </div>

            {/* Conversation Stream Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {events.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-2">
                  <Activity className="h-10 w-10 text-slate-600" />
                  <p className="text-sm">Waiting for incoming telemetry events...</p>
                </div>
              ) : (
                events.map((event, index) => {
                  const eventId = `${event.timestamp}-${index}`;
                  const isExpanded = expandedLlmCalls[eventId] || false;

                  if (event.type === "incoming_update") {
                    return (
                      <div key={eventId} className="flex justify-start max-w-2xl">
                        <div className="flex gap-3">
                          <div className="h-8 w-8 rounded-full bg-emerald-950 border border-emerald-500/30 flex items-center justify-center shrink-0">
                            <User className="h-4.5 w-4.5 text-emerald-400" />
                          </div>
                          <div>
                            <div className="text-xxs text-emerald-400 font-semibold mb-1 flex items-center gap-1">
                              <span>USER</span>
                              {event.username && (
                                <span className="text-slate-400 font-normal">
                                  @{event.username}
                                </span>
                              )}
                              <span className="text-slate-500 font-normal font-mono ml-1">
                                {formatTime(event.timestamp)}
                              </span>
                            </div>
                            <div className="bg-emerald-950/20 border border-emerald-500/20 px-4 py-3 rounded-2xl rounded-tl-none text-slate-200 text-sm whitespace-pre-wrap leading-relaxed shadow-sm">
                              {event.has_image && (
                                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold mb-2 bg-emerald-950/50 p-2 rounded-lg border border-emerald-500/10">
                                  <ImageIcon className="h-4 w-4 animate-pulse" />
                                  <span>[Food Photo Attached]</span>
                                </div>
                              )}
                              {event.text || (
                                <span className="text-emerald-500/70 italic">[No text]</span>
                              )}
                              {event.callback_data && (
                                <div className="mt-2 text-xxs font-mono bg-slate-900 border border-emerald-500/15 p-2 rounded-lg text-emerald-400">
                                  ⚡ Tapped option payload:{" "}
                                  <span className="text-slate-100 font-bold">
                                    "{event.callback_data}"
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  if (event.type === "outgoing_response") {
                    return (
                      <div key={eventId} className="flex justify-end max-w-2xl ml-auto">
                        <div className="flex gap-3 flex-row-reverse">
                          <div className="h-8 w-8 rounded-full bg-blue-950 border border-blue-500/30 flex items-center justify-center shrink-0">
                            <Bot className="h-4.5 w-4.5 text-blue-400" />
                          </div>
                          <div className="text-right">
                            <div className="text-xxs text-blue-400 font-semibold mb-1 flex items-center gap-1 justify-end">
                              <span className="text-slate-500 font-normal font-mono mr-1">
                                {formatTime(event.timestamp)}
                              </span>
                              <span>CALOBOT</span>
                            </div>
                            <div className="bg-blue-950/20 border border-blue-500/20 px-4 py-3 rounded-2xl rounded-tr-none text-slate-200 text-sm whitespace-pre-wrap leading-relaxed text-left shadow-sm inline-block">
                              <div dangerouslySetInnerHTML={{ __html: event.text }} />

                              {/* Render mock buttons if the keyboard options exist */}
                              {event.options && Object.keys(event.options).length > 0 && (
                                <div className="mt-3.5 pt-3.5 border-t border-blue-500/15 grid grid-cols-2 gap-2">
                                  {Object.entries(event.options).map(([label, callbackData]) => (
                                    <button
                                      key={label}
                                      disabled
                                      className="px-3 py-1.5 bg-blue-950/40 hover:bg-blue-900/40 border border-blue-500/25 rounded-xl text-xs font-medium text-blue-300 text-center transition-colors cursor-not-allowed truncate"
                                      title={`Payload: ${callbackData}`}
                                    >
                                      {label}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  if (event.type === "llm_transaction") {
                    const hasFailed = !event.success;
                    return (
                      <div
                        key={eventId}
                        className={`w-full rounded-2xl border transition-all ${
                          hasFailed
                            ? "bg-red-950/10 border-red-500/20 shadow-lg shadow-red-950/10"
                            : "bg-indigo-950/10 border-indigo-500/15 shadow-sm hover:border-indigo-500/25"
                        }`}
                      >
                        {/* Transaction Card Summary Bar */}
                        <div
                          onClick={() => toggleLlmExpand(eventId)}
                          className="p-4 flex items-center justify-between cursor-pointer select-none"
                        >
                          <div className="flex items-center gap-3">
                            <div
                              className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                                hasFailed
                                  ? "bg-red-950 border border-red-500/20 text-red-400"
                                  : "bg-indigo-950 border border-indigo-500/20 text-indigo-400"
                              }`}
                            >
                              <Brain className="h-4.5 w-4.5" />
                            </div>
                            <div className="flex flex-col md:flex-row md:items-center gap-1.5 md:gap-3">
                              <span className="font-bold text-sm text-slate-100 flex items-center gap-1">
                                LLM CALL: {event.step}
                              </span>
                              <div className="flex flex-wrap gap-1.5">
                                <span className="px-2 py-0.5 bg-slate-900 border border-slate-800 rounded text-xxs font-mono text-slate-400">
                                  {event.model}
                                </span>
                                {event.latency_seconds !== undefined && (
                                  <span className="px-2 py-0.5 bg-slate-900 border border-slate-800 rounded text-xxs font-mono text-slate-400 flex items-center gap-1">
                                    <Clock className="h-3 w-3 text-slate-500" />
                                    {event.latency_seconds.toFixed(2)}s
                                  </span>
                                )}
                                <span className="px-2 py-0.5 bg-slate-900 border border-slate-800 rounded text-xxs font-mono text-slate-400">
                                  Temp: {event.temperature}
                                </span>
                                {event.attempts_count > 1 && (
                                  <span className="px-2 py-0.5 bg-amber-950/30 border border-amber-500/20 rounded text-xxs font-semibold font-mono text-amber-400">
                                    Attempts: {event.attempts_count}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            {hasFailed ? (
                              <span className="flex items-center gap-1 bg-red-950/40 text-red-400 px-2 py-0.5 rounded text-xxs border border-red-500/20 font-bold">
                                <AlertTriangle className="h-3 w-3" />
                                Fail
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 bg-emerald-950/40 text-emerald-400 px-2 py-0.5 rounded text-xxs border border-emerald-500/20 font-bold">
                                <CheckCircle className="h-3 w-3" />
                                Success
                              </span>
                            )}
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4 text-slate-400" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-slate-400" />
                            )}
                          </div>
                        </div>

                        {/* Expandable Tabs Trace Area */}
                        {isExpanded && (
                          <div className="px-4 pb-4 border-t border-slate-800/60 pt-4 space-y-4 text-xs font-mono">
                            {/* General details */}
                            <div className="bg-slate-900/55 p-3 rounded-lg border border-slate-800/60 space-y-1">
                              <div>
                                <span className="text-slate-500 font-bold">Timestamp: </span>
                                <span className="text-slate-300">
                                  {formatFullDate(event.timestamp)}
                                </span>
                              </div>
                              {event.error && (
                                <div className="text-red-400 flex items-start gap-1 pt-1 border-t border-red-500/10 mt-1">
                                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                                  <span>
                                    <strong>Error Trace: </strong>
                                    {event.error}
                                  </span>
                                </div>
                              )}
                            </div>

                            {/* Prompts section */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                              <div className="space-y-1.5">
                                <span className="text-slate-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                  <Code className="h-3.5 w-3.5" /> System Prompt Instructions
                                </span>
                                <pre className="p-3 bg-slate-950 border border-slate-850 rounded-xl overflow-x-auto text-xxs text-slate-300 max-h-52 overflow-y-auto whitespace-pre-wrap leading-normal">
                                  {event.system_prompt}
                                </pre>
                              </div>
                              <div className="space-y-1.5">
                                <span className="text-slate-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                  <User className="h-3.5 w-3.5" /> Prompt Extraction Input
                                </span>
                                <pre className="p-3 bg-slate-950 border border-slate-850 rounded-xl overflow-x-auto text-xxs text-slate-300 max-h-52 overflow-y-auto whitespace-pre-wrap leading-normal">
                                  {event.prompt}
                                </pre>
                              </div>
                            </div>

                            {/* Schema description */}
                            {event.schema_json && (
                              <div className="space-y-1.5">
                                <span className="text-slate-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                  <Code className="h-3.5 w-3.5" /> Pydantic Schema ({event.schema_name})
                                </span>
                                <pre className="p-3 bg-slate-950 border border-slate-850 rounded-xl overflow-x-auto text-xxs text-slate-400 max-h-40 overflow-y-auto">
                                  {JSON.stringify(event.schema_json, null, 2)}
                                </pre>
                              </div>
                            )}

                            {/* Results section */}
                            {event.success && (
                              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div className="space-y-1.5">
                                  <span className="text-indigo-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                    <Bot className="h-3.5 w-3.5" /> Raw Response JSON String
                                  </span>
                                  <pre className="p-3 bg-slate-950 border border-indigo-950/20 rounded-xl overflow-x-auto text-xxs text-slate-300 max-h-52 overflow-y-auto whitespace-pre-wrap">
                                    {event.response_raw}
                                  </pre>
                                </div>
                                <div className="space-y-1.5">
                                  <span className="text-emerald-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                    <CheckCircle className="h-3.5 w-3.5" /> Validated JSON Structure
                                  </span>
                                  <pre className="p-3 bg-slate-950 border border-emerald-950/20 rounded-xl overflow-x-auto text-xxs text-emerald-300 max-h-52 overflow-y-auto">
                                    {JSON.stringify(event.response_parsed, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            )}

                            {/* Intercepted Retry Logs */}
                            {event.validation_attempts && event.validation_attempts.length > 0 && (
                              <div className="space-y-1.5">
                                <span className="text-amber-400 font-bold uppercase tracking-wider text-xxs flex items-center gap-1">
                                  <AlertTriangle className="h-3.5 w-3.5" /> Multi-Turn Validation Retries
                                </span>
                                <div className="space-y-2 max-h-60 overflow-y-auto">
                                  {event.validation_attempts.map((att: any, attIndex: number) => (
                                    <div
                                      key={attIndex}
                                      className="p-3 bg-amber-950/10 border border-amber-500/15 rounded-xl space-y-2 text-xxs text-amber-350"
                                    >
                                      <div>
                                        <span className="font-bold">Attempt #{att.attempt} Raw Reply:</span>
                                        <pre className="mt-1 p-2 bg-slate-950 border border-amber-500/10 rounded-lg text-slate-300 overflow-x-auto">
                                          {att.raw_response}
                                        </pre>
                                      </div>
                                      <div>
                                        <span className="font-bold text-red-400">Pydantic Exception Raised:</span>
                                        <pre className="mt-1 p-2 bg-slate-950 border border-red-500/10 rounded-lg text-red-300 overflow-x-auto whitespace-pre-wrap">
                                          {att.error}
                                        </pre>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  }

                  return null;
                })
              )}
              <div ref={eventsEndRef} />
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-2">
            <Activity className="h-12 w-12 text-slate-700 animate-pulse" />
            <h3 className="font-bold text-lg text-slate-300">No Session Selected</h3>
            <p className="text-sm">Choose a chat_id from the sidebar to view its activity trace</p>
          </div>
        )}
      </div>
    </div>
  );
}
