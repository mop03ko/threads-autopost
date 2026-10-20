// Cloudflare provides a second clock, while Actions owns all publishing.
// This Worker never reads queue.json and never calls the Threads API.
export async function dispatchScheduled(env) {
  if (env.DISPATCH_ENABLED === "false") return { status: "disabled" };
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN тохируулаагүй байна");
  const owner = encodeURIComponent(env.GITHUB_OWNER || "mop03ko");
  const repo = encodeURIComponent(env.GITHUB_REPO || "threads-autopost");
  const workflow = encodeURIComponent(env.GITHUB_WORKFLOW || "threads-post.yml");
  let response;
  try {
    response = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
          "User-Agent": "threads-autopost-scheduler",
        },
        // No post_id: scheduled invocations must always respect due times.
        body: JSON.stringify({ ref: env.GITHUB_BRANCH || "main" }),
        signal: AbortSignal.timeout(15000),
      },
    );
  } catch {
    throw new Error("GitHub workflow dispatch сүлжээний алдаа");
  }
  if (response.status !== 204) {
    throw new Error(`GitHub workflow dispatch HTTP ${response.status}`);
  }
  return { status: "dispatched" }; // Accepted, not confirmation of publication.
}

export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/health") {
      return new Response("Not found", { status: 404 });
    }
    const enabled = env.DISPATCH_ENABLED !== "false";
    const configured = Boolean(env.GITHUB_TOKEN);
    return Response.json({
      service: "threads-autopost-dispatch",
      enabled,
      configured,
      // Publication results are reported in Actions and queue.json.
    }, { status: enabled && configured ? 200 : 503 });
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(dispatchScheduled(env).then(result => {
      console.log(JSON.stringify({ event: "schedule", ...result }));
    }).catch(error => {
      console.error(error.message);
      throw error;
    }));
  },
};
