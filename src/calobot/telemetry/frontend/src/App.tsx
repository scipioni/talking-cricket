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
  Lock,
  LogOut,
  BarChart2,
  TrendingUp,
  Server,
} from "lucide-react";

// Types representing our telemetry events
interface TelemetryEvent {
  type: "incoming_update" | "outgoing_response" | "llm_transaction";
  chat_id: number | string;
  timestamp: string;
  [key: string]: any;
}

interface ActiveSession {
  chat_id: number | string;
  last_active: string;
  event_count: number;
}

interface AuthState {
  authenticated: boolean;
  email: string | null;
}

interface PublicMetrics {
  active_sessions_count: number;
  avg_latencies: Record<string, number>;
  intent_distribution: Record<string, number>;
  sessions: ActiveSession[];
  recent_events: TelemetryEvent[];
}

export default function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const [auth, setAuth] = useState<AuthState>({ authenticated: false, email: null });
  const [authLoading, setAuthLoading] = useState(true);

  // Private states
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<number | string | null>(null);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedLlmCalls, setExpandedLlmCalls] = useState<Record<string, boolean>>({});

  // Public states
  const [publicMetrics, setPublicMetrics] = useState<PublicMetrics | null>(null);
  const [publicEvents, setPublicEvents] = useState<TelemetryEvent[]>([]);
  const [publicConnected, setPublicConnected] = useState(false);

  const eventsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Path listener
  useEffect(() => {
    const handlePopState = () => setCurrentPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigateTo = (path: string) => {
    window.history.pushState({}, "", path);
    setCurrentPath(path);
  };

  // Check auth session
  useEffect(() => {
    fetchAuth();
  }, []);

  const fetchAuth = async () => {
    try {
      const res = await fetch("/api/auth/session");
      if (res.ok) {
        const data = await res.json();
        setAuth(data);
      }
    } catch (err) {
      console.error("Failed to check auth status:", err);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      const res = await fetch("/api/auth/logout", { method: "POST" });
      if (res.ok) {
        setAuth({ authenticated: false, email: null });
        navigateTo("/");
      }
    } catch (err) {
      console.error("Failed to log out:", err);
    }
  };

  // --- PUBLIC CONTROLLER ---
  useEffect(() => {
    if (currentPath !== "/") return;

    // Fetch initial public metrics
    const fetchPublicMetrics = async () => {
      try {
        const res = await fetch("/api/public/metrics");
        if (res.ok) {
          const data: PublicMetrics = await res.json();
          setPublicMetrics(data);
          setPublicEvents(data.recent_events || []);
        }
      } catch (err) {
        console.error("Failed to fetch public metrics:", err);
      }
    };

    fetchPublicMetrics();

    // Connect to public WS
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8083";
    const wsUrl = `${protocol}//${host}/telemetry/public/ws`;

    console.log("Connecting to public WebSocket:", wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setPublicConnected(true);
      console.log("Public WS connected.");
    };

    ws.onclose = () => {
      setPublicConnected(false);
      console.log("Public WS closed.");
    };

    ws.onmessage = (messageEvent) => {
      try {
        const event: TelemetryEvent = JSON.parse(messageEvent.data);
        setPublicEvents((prev) => {
          const updated = [...prev, event];
          return updated.slice(-50); // Keep last 50
        });
      } catch (err) {
        console.error("Error parsing public WS message:", err);
      }
    };

    return () => {
      ws.close();
    };
  }, [currentPath]);

  // --- PRIVATE CONTROLLER ---
  useEffect(() => {
    if (currentPath !== "/private" || !auth.authenticated) return;

    fetchSessions();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8083";
    const wsUrl = `${protocol}//${host}/telemetry/ws`;

    const connectWs = () => {
      console.log("Connecting to private WebSocket:", wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        console.log("Private WS connected.");
      };

      ws.onclose = () => {
        setConnected(false);
        console.log("Private WS closed. Retrying in 3s...");
        setTimeout(connectWs, 3000);
      };

      ws.onmessage = (messageEvent) => {
        try {
          const event: TelemetryEvent = JSON.parse(messageEvent.data);
          const eventChatId = event.chat_id;

          setEvents((prev) => {
            if (activeChatId === eventChatId) {
              return [...prev, event];
            }
            return prev;
          });

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

            return updated.sort(
              (a, b) => new Date(b.last_active).getTime() - new Date(a.last_active).getTime()
            );
          });
        } catch (err) {
          console.error("Error parsing private WS message:", err);
        }
      };
    };

    connectWs();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [currentPath, auth.authenticated, activeChatId]);

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

  const selectSession = async (chatId: number | string) => {
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

  // Scroll to bottom
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, publicEvents]);

  const toggleLlmExpand = (eventId: string) => {
    setExpandedLlmCalls((prev) => ({
      ...prev,
      [eventId]: !prev[eventId],
    }));
  };

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

  if (authLoading) {
    return (
      <div className="flex h-screen w-screen bg-slate-950 items-center justify-center text-slate-400 font-sans">
        <div className="flex flex-col items-center gap-3">
          <Activity className="h-10 w-10 text-indigo-500 animate-pulse" />
          <p className="text-sm font-medium">Verifying active sessions...</p>
        </div>
      </div>
    );
  }

  // --- PUBLIC VIEW (Landing) ---
  if (currentPath === "/") {
    const totalEvents = publicEvents.length;
    const avgResponseTime =
      publicMetrics && Object.keys(publicMetrics.avg_latencies).length > 0
        ? (
            Object.values(publicMetrics.avg_latencies).reduce((a, b) => a + b, 0) /
            Object.keys(publicMetrics.avg_latencies).length
          ).toFixed(2)
        : "0.00";

    return (
      <div className="flex flex-col h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
        {/* Public Header */}
        <header className="h-16 border-b border-slate-800 bg-slate-900/80 px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <Activity className="h-6 w-6 text-indigo-400" />
            <h1 className="font-bold text-lg text-slate-50 tracking-wide">Calobot Public Dashboard</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 bg-slate-950/60 px-3 py-1 rounded-full text-xs border border-slate-850">
              <span className={`h-2 w-2 rounded-full ${publicConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
              <span className="text-slate-400 font-semibold">{publicConnected ? "Live" : "Offline"}</span>
            </div>
            {auth.authenticated ? (
              <div className="flex items-center gap-3">
                <button
                  onClick={() => navigateTo("/private")}
                  className="flex items-center gap-2 bg-indigo-650 hover:bg-indigo-600 transition-colors px-3 py-1.5 rounded-lg text-xs font-semibold"
                >
                  <Server className="h-4 w-4" />
                  Admin Console
                </button>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1.5 text-slate-400 hover:text-red-400 transition-colors text-xs font-medium"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            ) : (
              <button
                onClick={() => navigateTo("/private")}
                className="flex items-center gap-2 bg-slate-850 hover:bg-slate-800 border border-slate-700 hover:border-indigo-500/40 transition-all px-4 py-1.5 rounded-xl text-xs font-semibold text-slate-200"
              >
                <Lock className="h-3.5 w-3.5 text-slate-400" />
                Sign in
              </button>
            )}
          </div>
        </header>

        {/* Public Main Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Stats Cards Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-5 bg-slate-900 border border-slate-800/80 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Active Sessions</span>
                <h3 className="text-3xl font-black text-slate-100 mt-1">
                  {publicMetrics?.active_sessions_count || 0}
                </h3>
              </div>
              <div className="h-11 w-11 bg-indigo-950/40 border border-indigo-500/10 rounded-xl flex items-center justify-center text-indigo-400">
                <Server className="h-5 w-5" />
              </div>
            </div>
            <div className="p-5 bg-slate-900 border border-slate-800/80 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Avg Model Latency</span>
                <h3 className="text-3xl font-black text-slate-100 mt-1">{avgResponseTime}s</h3>
              </div>
              <div className="h-11 w-11 bg-emerald-950/40 border border-emerald-500/10 rounded-xl flex items-center justify-center text-emerald-400">
                <Clock className="h-5 w-5" />
              </div>
            </div>
            <div className="p-5 bg-slate-900 border border-slate-800/80 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Total Stream Events</span>
                <h3 className="text-3xl font-black text-slate-100 mt-1">{totalEvents}</h3>
              </div>
              <div className="h-11 w-11 bg-amber-950/40 border border-amber-500/10 rounded-xl flex items-center justify-center text-amber-400">
                <TrendingUp className="h-5 w-5" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* System Breakdown Panel */}
            <div className="lg:col-span-1 p-5 bg-slate-900 border border-slate-800/80 rounded-2xl space-y-6 flex flex-col justify-between">
              <div>
                <h3 className="font-bold text-slate-200 flex items-center gap-2">
                  <BarChart2 className="h-4.5 w-4.5 text-indigo-400" />
                  NLP Intent Distribution
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">Frequency of processed user logging intents</p>
                <div className="mt-5 space-y-3.5">
                  {publicMetrics && Object.keys(publicMetrics.intent_distribution).length > 0 ? (
                    Object.entries(publicMetrics.intent_distribution).map(([intent, count]) => {
                      const total = Object.values(publicMetrics.intent_distribution).reduce((a, b) => a + b, 0);
                      const pct = ((count / total) * 100).toFixed(0);
                      return (
                        <div key={intent} className="space-y-1">
                          <div className="flex justify-between text-xs font-medium">
                            <span className="text-slate-300 font-mono capitalize">{intent}</span>
                            <span className="text-slate-400">
                              {count} ({pct}%)
                            </span>
                          </div>
                          <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-center py-6 text-slate-600 text-xs">Waiting for live interactions...</div>
                  )}
                </div>
              </div>

              <div className="pt-4 border-t border-slate-800/50">
                <h3 className="font-bold text-slate-200 flex items-center gap-2">
                  <Brain className="h-4.5 w-4.5 text-emerald-400" />
                  Step-by-Step Performance
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">Average execution speed by model pipeline step</p>
                <div className="mt-4 space-y-3.5">
                  {publicMetrics && Object.keys(publicMetrics.avg_latencies).length > 0 ? (
                    Object.entries(publicMetrics.avg_latencies).map(([step, val]) => (
                      <div key={step} className="flex justify-between items-center text-xs">
                        <span className="text-slate-400 font-mono capitalize">{step.replace("_", " ")}</span>
                        <span className="font-semibold text-emerald-400 font-mono bg-emerald-950/20 border border-emerald-500/10 px-2 py-0.5 rounded">
                          {val.toFixed(2)}s
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-6 text-slate-600 text-xs">Waiting for pipeline traces...</div>
                  )}
                </div>
              </div>
            </div>

            {/* Scrubbed Live Event stream */}
            <div className="lg:col-span-2 p-5 bg-slate-900 border border-slate-800/80 rounded-2xl flex flex-col h-[500px]">
              <h3 className="font-bold text-slate-200 mb-0.5 flex items-center gap-2">
                <Activity className="h-4.5 w-4.5 text-rose-400 animate-pulse" />
                Live Anonymized Event Log
              </h3>
              <p className="text-xs text-slate-500 mb-4">
                Real-time activity log completely scrubbed of user names, raw text, and model prompts
              </p>

              <div className="flex-1 overflow-y-auto space-y-3.5 pr-2">
                {publicEvents.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-slate-600 text-sm gap-2">
                    <Activity className="h-8 w-8 text-slate-800" />
                    <p>No activity recorded since server boot.</p>
                  </div>
                ) : (
                  publicEvents.map((event, index) => {
                    const eventId = `${event.timestamp}-${index}`;
                    const time = formatTime(event.timestamp);

                    if (event.type === "incoming_update") {
                      return (
                        <div key={eventId} className="flex items-start gap-3 bg-slate-950/30 p-3 rounded-xl border border-slate-850/50">
                          <div className="h-7 w-7 rounded-full bg-emerald-950/40 border border-emerald-500/25 flex items-center justify-center shrink-0">
                            <User className="h-3.5 w-3.5 text-emerald-400" />
                          </div>
                          <div className="text-xs">
                            <div className="font-semibold text-emerald-400 flex items-center gap-2">
                              <span>User (Anonymized)</span>
                              <span className="text-slate-600 font-mono font-normal">#{event.chat_id}</span>
                              <span className="text-slate-600 font-mono font-normal">{time}</span>
                            </div>
                            <p className="text-slate-400 mt-1 italic text-xxs bg-emerald-950/5 border border-emerald-500/5 px-2.5 py-1.5 rounded-lg inline-block">
                              {event.text}
                            </p>
                          </div>
                        </div>
                      );
                    }

                    if (event.type === "outgoing_response") {
                      return (
                        <div key={eventId} className="flex items-start gap-3 bg-slate-950/30 p-3 rounded-xl border border-slate-850/50">
                          <div className="h-7 w-7 rounded-full bg-blue-950/40 border border-blue-500/25 flex items-center justify-center shrink-0">
                            <Bot className="h-3.5 w-3.5 text-blue-400" />
                          </div>
                          <div className="text-xs">
                            <div className="font-semibold text-blue-400 flex items-center gap-2">
                              <span>Calobot</span>
                              <span className="text-slate-600 font-mono font-normal">#{event.chat_id}</span>
                              <span className="text-slate-600 font-mono font-normal">{time}</span>
                            </div>
                            <p className="text-slate-400 mt-1 italic text-xxs bg-blue-950/5 border border-blue-500/5 px-2.5 py-1.5 rounded-lg inline-block">
                              {event.text}
                            </p>
                          </div>
                        </div>
                      );
                    }

                    if (event.type === "llm_transaction") {
                      return (
                        <div key={eventId} className="flex items-start gap-3 bg-slate-950/30 p-3 rounded-xl border border-slate-850/50">
                          <div className="h-7 w-7 rounded-full bg-indigo-950/40 border border-indigo-500/25 flex items-center justify-center shrink-0">
                            <Brain className="h-3.5 w-3.5 text-indigo-400" />
                          </div>
                          <div className="text-xs">
                            <div className="font-semibold text-indigo-400 flex items-center gap-2">
                              <span>LLM Decision Step</span>
                              <span className="text-slate-600 font-mono font-normal">#{event.chat_id}</span>
                              <span className="text-slate-600 font-mono font-normal">{time}</span>
                            </div>
                            <div className="mt-1 flex flex-wrap gap-2 text-xxs font-mono">
                              <span className="text-slate-400 bg-slate-950 border border-slate-850 px-2 py-0.5 rounded capitalize">
                                Step: {event.step}
                              </span>
                              <span className="text-slate-400 bg-slate-950 border border-slate-850 px-2 py-0.5 rounded">
                                Model: {event.model}
                              </span>
                              {event.latency_seconds !== undefined && (
                                <span className="text-emerald-400 bg-slate-950 border border-emerald-950/20 px-2 py-0.5 rounded">
                                  Speed: {event.latency_seconds.toFixed(2)}s
                                </span>
                              )}
                              <span
                                className={`px-2 py-0.5 rounded font-semibold border ${
                                  event.success
                                    ? "bg-emerald-950/20 border-emerald-500/10 text-emerald-400"
                                    : "bg-red-950/20 border-red-500/10 text-red-400"
                                }`}
                              >
                                {event.success ? "Success" : "Failed"}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    }

                    return null;
                  })
                )}
                <div ref={eventsEndRef} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- PRIVATE ADMIN GUARD & LOGIN CARD ---
  if (currentPath === "/private" && !auth.authenticated) {
    return (
      <div className="flex h-screen w-screen bg-slate-950 items-center justify-center text-slate-400 font-sans p-4">
        <div className="max-w-md w-full p-8 bg-slate-900 border border-slate-800 rounded-3xl text-center space-y-6 shadow-2xl shadow-indigo-950/10">
          <div className="h-16 w-16 bg-indigo-950/50 border border-indigo-500/20 rounded-2xl flex items-center justify-center text-indigo-400 mx-auto">
            <Lock className="h-7 w-7" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black text-slate-100 tracking-tight">Admin Authentication Required</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              This space contains unscrubbed active user chat logs, detailed database entry trace histories, and raw prompt completions.
            </p>
          </div>
          <div className="pt-4 border-t border-slate-800/80">
            <a
              href="/api/auth/login"
              className="w-full flex items-center justify-center gap-3 bg-white hover:bg-slate-100 text-slate-900 transition-colors py-3 px-5 rounded-2xl text-sm font-bold shadow-md cursor-pointer"
            >
              <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24">
                <path
                  fill="#EA4335"
                  d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.414 0-6.19-2.77-6.19-6.19 0-3.42 2.777-6.19 6.19-6.19 1.483 0 2.825.524 3.876 1.404l3.125-3.124C18.847 1.94 15.776 1 12.24 1 6.12 1 1.16 6.12 1.16 12.24s4.96 11.24 11.08 11.24c5.77 0 10.74-4.14 10.74-11.24 0-.768-.082-1.5-.233-1.955H12.24z"
                />
              </svg>
              Sign in with Google
            </a>
            <button
              onClick={() => navigateTo("/")}
              className="mt-3 text-xs text-slate-500 hover:text-slate-300 transition-colors font-medium"
            >
              Back to Public Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- PRIVATE ADMIN VIEW (Authenticated) ---
  const filteredSessions = sessions.filter((s) => s.chat_id.toString().includes(searchTerm));

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
            <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
            <span className="text-slate-400 font-medium">{connected ? "Live" : "Offline"}</span>
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
            <div className="text-center py-8 text-slate-500 text-sm">No sessions found</div>
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
                    <span className="font-semibold text-sm text-slate-200">ID: {session.chat_id}</span>
                    <span className="text-xxs text-slate-400 font-mono">{formatTime(session.last_active)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {session.event_count} telemetry traces
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/30 flex items-center justify-between text-xs text-slate-400">
          <div className="flex flex-col truncate">
            <span className="font-bold text-slate-200 truncate">{auth.email}</span>
            <span>Administrator Session</span>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 text-slate-500 hover:text-red-400 transition-colors"
            title="Sign Out"
          >
            <LogOut className="h-4.5 w-4.5" />
          </button>
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
              <div className="flex gap-3">
                <button
                  onClick={() => navigateTo("/")}
                  className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-750 transition-colors text-slate-200 px-3.5 py-1.5 rounded-lg text-sm font-semibold border border-slate-700"
                >
                  <Server className="h-4 w-4" />
                  View Public Board
                </button>
                <a
                  href={`/api/export/${activeChatId}`}
                  download={`session_${activeChatId}_activity.json`}
                  className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 transition-colors text-white px-3.5 py-1.5 rounded-lg text-sm font-semibold shadow-md cursor-pointer"
                >
                  <Download className="h-4 w-4" />
                  Export Activity JSON
                </a>
              </div>
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
                              {event.username && <span className="text-slate-400 font-normal">@{event.username}</span>}
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
                              {event.text || <span className="text-emerald-500/70 italic">[No text]</span>}
                              {event.callback_data && (
                                <div className="mt-2 text-xxs font-mono bg-slate-900 border border-emerald-500/15 p-2 rounded-lg text-emerald-400">
                                  ⚡ Tapped option payload:{" "}
                                  <span className="text-slate-100 font-bold">"{event.callback_data}"</span>
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

                        {isExpanded && (
                          <div className="px-4 pb-4 border-t border-slate-800/60 pt-4 space-y-4 text-xs font-mono">
                            <div className="bg-slate-900/55 p-3 rounded-lg border border-slate-800/60 space-y-1">
                              <div>
                                <span className="text-slate-500 font-bold">Timestamp: </span>
                                <span className="text-slate-300">{formatFullDate(event.timestamp)}</span>
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
