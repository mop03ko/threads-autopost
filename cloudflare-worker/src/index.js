const GRAPH = "https://graph.threads.net/v1.0";
const REFRESH_URL = "https://graph.threads.net/refresh_access_token";
const LOCAL_OFFSET = "+08:00";
const DEFAULT_GRACE_MINUTES = 150;
const DEFAULT_MAX_POSTS_PER_RUN = 3;
const DEFAULT_MAX_POSTS_PER_DAY = 15;

class HttpError extends Error {
  constructor(message, status, body = "") {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.body = body;
  }
}

function config(env) {
  return {
    owner: env.GITHUB_OWNER || "mop03ko",
    repo: env.GITHUB_REPO || "threads-autopost",
    branch: env.GITHUB_BRANCH || "main",
    queuePath: env.QUEUE_PATH || "queue.json",
    graceMinutes: Number(env.LATE_GRACE_MINUTES || DEFAULT_GRACE_MINUTES),
    maxPostsPerRun: Number(env.MAX_POSTS_PER_RUN || DEFAULT_MAX_POSTS_PER_RUN),
    maxPostsPerDay: Number(env.MAX_POSTS_PER_DAY || DEFAULT_MAX_POSTS_PER_DAY),
  };
}

function log(event, fields = {}) {
  console.log(JSON.stringify({ event, ...fields }));
}

function localTimestamp(date = new Date()) {
  const shifted = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  return shifted.toISOString().slice(0, 16).replace("T", " ");
}

function parseScheduledAt(value) {
  const match = String(value || "").match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (!match) return Number.NaN;
  const seconds = match[6] || "00";
  return Date.parse(
    `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${seconds}${LOCAL_OFFSET}`,
  );
}

function encodeBase64Utf8(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function decodeBase64Utf8(value) {
  const binary = atob(String(value).replace(/\s/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

function githubPath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

async function githubRequest(env, path, init = {}) {
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN secret тохируулаагүй байна");
  const response = await fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "threads-autopost-cloudflare-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
  const body = await response.text();
  if (!response.ok) {
    throw new HttpError(
      `GitHub API ${init.method || "GET"} ${path} -> HTTP ${response.status}`,
      response.status,
      body.slice(0, 500),
    );
  }
  return body ? JSON.parse(body) : {};
}

async function readQueue(env) {
  const cfg = config(env);
  const data = await githubRequest(
    env,
    `/repos/${encodeURIComponent(cfg.owner)}/${encodeURIComponent(cfg.repo)}/contents/${githubPath(cfg.queuePath)}?ref=${encodeURIComponent(cfg.branch)}`,
  );
  if (data.type !== "file" || !data.sha || !data.content) {
    throw new Error("queue.json GitHub-оос бүрэн уншигдсангүй");
  }
  const queue = JSON.parse(decodeBase64Utf8(data.content));
  if (!Array.isArray(queue)) throw new Error("queue.json жагсаалт биш байна");
  return { queue, sha: data.sha };
}

async function writeQueue(env, queue, sha, message) {
  const cfg = config(env);
  return githubRequest(
    env,
    `/repos/${encodeURIComponent(cfg.owner)}/${encodeURIComponent(cfg.repo)}/contents/${githubPath(cfg.queuePath)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        message,
        content: encodeBase64Utf8(`${JSON.stringify(queue, null, 2)}\n`),
        branch: cfg.branch,
        sha,
      }),
    },
  );
}

function selectDuePosts(queue, nowMs, cfg) {
  const graceMs = cfg.graceMinutes * 60 * 1000;
  const today = localTimestamp(new Date(nowMs)).slice(0, 10);
  const postedToday = queue.filter(
    (post) => post.status === "posted" && String(post.posted_at || "").startsWith(today),
  ).length;
  const budget = Math.max(
    0,
    Math.min(cfg.maxPostsPerRun, cfg.maxPostsPerDay - postedToday),
  );
  const due = [];
  const stale = [];
  for (const post of queue) {
    if (post.status !== "pending") continue;
    const scheduledMs = parseScheduledAt(post.scheduled_at);
    if (!Number.isFinite(scheduledMs) || scheduledMs > nowMs) continue;
    if (nowMs - scheduledMs > graceMs) stale.push(post);
    else due.push(post);
  }
  due.sort((a, b) => parseScheduledAt(a.scheduled_at) - parseScheduledAt(b.scheduled_at));
  return { selected: due.slice(0, budget), stale };
}

async function claimDuePosts(env, nowMs) {
  const cfg = config(env);
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const { queue, sha } = await readQueue(env);
    const { selected, stale } = selectDuePosts(queue, nowMs, cfg);

    for (const post of stale) {
      post.status = "skipped";
      post.note = `${cfg.graceMinutes} минутаас их хоцорсон тул алгассан`;
    }

    if (selected.length === 0 && stale.length === 0) {
      return { claims: [], finalizedOnly: false };
    }

    const claimToken = crypto.randomUUID();
    const processingAt = localTimestamp(new Date(nowMs));
    for (const post of selected) {
      post.status = "processing";
      post.processing_token = claimToken;
      post.processing_at = processingAt;
      delete post.error;
      delete post.note;
    }

    const ids = selected.map((post) => post.id);
    const message = ids.length
      ? `Threads post claimed: ${ids.join(", ")}`
      : "Threads post finalized: overdue posts skipped";
    try {
      await writeQueue(env, queue, sha, message);
      return {
        claims: selected.map((post) => ({ ...post })),
        claimToken,
        finalizedOnly: selected.length === 0 && stale.length > 0,
      };
    } catch (error) {
      if (error instanceof HttpError && (error.status === 409 || error.status === 422)) {
        log("queue_claim_conflict", { attempt });
        continue;
      }
      throw error;
    }
  }
  throw new Error("queue.json-г 3 оролдлогоор claim хийж чадсангүй");
}

async function metaRequest(url, init = {}) {
  const response = await fetch(url, init);
  const body = await response.text();
  let data = {};
  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    throw new HttpError(`Threads API JSON биш хариу өглөө`, response.status, body.slice(0, 500));
  }
  if (!response.ok || data.error) {
    const message = data?.error?.message || body.slice(0, 500) || "үл мэдэгдэх алдаа";
    throw new HttpError(`Threads API HTTP ${response.status}: ${message}`, response.status, body.slice(0, 500));
  }
  return data;
}

async function loadAccessToken(env) {
  if (!env.THREADS_ACCESS_TOKEN) {
    throw new Error("THREADS_ACCESS_TOKEN secret тохируулаагүй байна");
  }

  let state = null;
  if (env.STATE) {
    try {
      state = await env.STATE.get("threads_token", "json");
    } catch (error) {
      log("token_state_read_failed", { error: String(error).slice(0, 300) });
    }
  }

  let accessToken = state?.accessToken || env.THREADS_ACCESS_TOKEN;
  const nowMs = Date.now();
  if (!env.STATE || Number(state?.nextRefreshAt || 0) > nowMs) return accessToken;

  try {
    const url = new URL(REFRESH_URL);
    url.searchParams.set("grant_type", "th_refresh_token");
    url.searchParams.set("access_token", accessToken);
    const refreshed = await metaRequest(url.toString());
    accessToken = refreshed.access_token;
    const expiresIn = Number(refreshed.expires_in || 60 * 86400);
    await env.STATE.put(
      "threads_token",
      JSON.stringify({
        accessToken,
        expiresAt: nowMs + expiresIn * 1000,
        nextRefreshAt: nowMs + Math.min(30 * 86400, expiresIn / 2) * 1000,
      }),
    );
    log("threads_token_refreshed", { expiresIn });
  } catch (error) {
    log("threads_token_refresh_failed", { error: String(error).slice(0, 300) });
    try {
      await env.STATE.put(
        "threads_token",
        JSON.stringify({ accessToken, nextRefreshAt: nowMs + 24 * 60 * 60 * 1000 }),
      );
    } catch (stateError) {
      log("token_state_write_failed", { error: String(stateError).slice(0, 300) });
    }
  }
  return accessToken;
}

async function resolveThreadsUserId(env, accessToken) {
  if (env.THREADS_USER_ID) return env.THREADS_USER_ID;
  const url = new URL(`${GRAPH}/me`);
  url.searchParams.set("fields", "id");
  url.searchParams.set("access_token", accessToken);
  const me = await metaRequest(url.toString());
  if (!me.id) throw new Error("Threads хэрэглэгчийн ID олдсонгүй");
  return me.id;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function publishOne(post, userId, accessToken) {
  const text = String(post.text || "");
  if (!text) throw new Error("Постын бичвэр хоосон байна");
  if (text.length > 500) throw new Error(`${text.length} тэмдэгттэй; Threads-ийн хязгаар 500`);

  const createBody = new URLSearchParams({
    access_token: accessToken,
    text,
    media_type: post.image_url ? "IMAGE" : "TEXT",
  });
  if (post.image_url) createBody.set("image_url", post.image_url);

  const container = await metaRequest(`${GRAPH}/${encodeURIComponent(userId)}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: createBody,
  });
  if (!container.id) throw new Error("Threads контейнерийн ID ирсэнгүй");

  const deadline = Date.now() + 60 * 1000;
  let containerReady = false;
  while (Date.now() < deadline) {
    await sleep(3000);
    const statusUrl = new URL(`${GRAPH}/${encodeURIComponent(container.id)}`);
    statusUrl.searchParams.set("fields", "id,status,error_message");
    statusUrl.searchParams.set("access_token", accessToken);
    const status = await metaRequest(statusUrl.toString());
    if (status.status === "FINISHED") {
      containerReady = true;
      break;
    }
    if (["ERROR", "EXPIRED"].includes(status.status)) {
      throw new Error(`Threads контейнер ${status.status}: ${status.error_message || "тайлбаргүй"}`);
    }
  }
  if (!containerReady) {
    throw new Error("Threads контейнер 60 секундэд бэлэн болсонгүй");
  }

  const publishBody = new URLSearchParams({
    access_token: accessToken,
    creation_id: container.id,
  });
  const published = await metaRequest(
    `${GRAPH}/${encodeURIComponent(userId)}/threads_publish`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: publishBody,
    },
  );
  if (!published.id) throw new Error("Нийтлэгдсэн Threads постын ID ирсэнгүй");
  return published.id;
}

async function finalizeClaims(env, claimToken, results) {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const { queue, sha } = await readQueue(env);
    let changed = 0;
    for (const result of results) {
      const post = queue.find(
        (item) => item.id === result.id
          && item.status === "processing"
          && item.processing_token === claimToken,
      );
      if (!post) continue;
      post.status = result.status;
      delete post.processing_token;
      delete post.processing_at;
      if (result.status === "posted") {
        post.posted_at = localTimestamp();
        post.threads_id = result.threadsId;
        delete post.error;
      } else {
        post.error = String(result.error || "үл мэдэгдэх алдаа").slice(0, 500);
      }
      changed += 1;
    }
    if (changed === 0) return;
    try {
      await writeQueue(
        env,
        queue,
        sha,
        `Threads post finalized: ${results.map((item) => item.id).join(", ")}`,
      );
      return;
    } catch (error) {
      if (error instanceof HttpError && (error.status === 409 || error.status === 422)) {
        log("queue_finalize_conflict", { attempt });
        continue;
      }
      throw error;
    }
  }
  throw new Error("Нийтэлсэн төлвийг queue.json-д 3 оролдлогоор хадгалж чадсангүй");
}

async function runScheduled(env, scheduledTime) {
  const runId = crypto.randomUUID();
  const nowMs = scheduledTime || Date.now();
  log("run_started", { runId, localTime: localTimestamp(new Date(nowMs)) });

  const claim = await claimDuePosts(env, nowMs);
  if (claim.claims.length === 0) {
    log("run_finished", {
      runId,
      result: claim.finalizedOnly ? "overdue_skipped" : "nothing_due",
    });
    return;
  }

  const accessToken = await loadAccessToken(env);
  const userId = await resolveThreadsUserId(env, accessToken);
  const results = [];
  for (const post of claim.claims) {
    try {
      const threadsId = await publishOne(post, userId, accessToken);
      results.push({ id: post.id, status: "posted", threadsId });
      log("post_published", { runId, postId: post.id, threadsId });
    } catch (error) {
      results.push({ id: post.id, status: "failed", error: String(error) });
      log("post_failed", { runId, postId: post.id, error: String(error).slice(0, 500) });
    }
  }
  await finalizeClaims(env, claim.claimToken, results);
  log("run_finished", { runId, result: "finalized", count: results.length });
}

export default {
  async fetch(request) {
    if (new URL(request.url).pathname !== "/health") {
      return new Response("Not found", { status: 404 });
    }
    return Response.json({
      ok: true,
      service: "threads-autopost-direct",
      localTime: localTimestamp(),
    });
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      runScheduled(env, controller.scheduledTime).catch((error) => {
        log("run_failed", { error: String(error).slice(0, 1000) });
        throw error;
      }),
    );
  },
};

export { localTimestamp, parseScheduledAt, selectDuePosts };
