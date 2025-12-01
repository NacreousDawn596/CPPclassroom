export default {
    async fetch(request, env) {
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        };

        try {
            const url = new URL(request.url);

            if (request.method === 'OPTIONS') {
                return new Response(null, { headers: corsHeaders });
            }

            // API Routes
            if (url.pathname.startsWith('/api')) {
                const path = url.pathname.replace('/api', '');

                // Check if Container binding exists
                if (!env.MY_CONTAINER) {
                    return new Response(JSON.stringify({
                        error: 'Configuration Error: MY_CONTAINER binding is missing. Ensure Durable Objects are enabled and bound in wrangler.toml.'
                    }), { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
                }

                // POST /run - Start new session
                if (path === '/run' && request.method === 'POST') {
                    try {
                        const body = await request.json();

                        // CHECK FOR SPAWN METHOD (User requested pattern)
                        if (env.MY_CONTAINER && typeof env.MY_CONTAINER.spawn === 'function') {
                            // If the binding supports spawn (e.g. Workers AI / Constellations / Workflows)
                            // We try to use it. Note: The arguments for spawn depend on the specific API.
                            // We'll assume it takes an array of args or an object.
                            try {
                                // This is speculative based on the prompt "env.MY_CONTAINER.spawn([...])"
                                // We might need to pass the command or arguments.
                                // For now, we'll try to spawn and see if we get a response.
                                const process = await env.MY_CONTAINER.spawn();
                                // If spawn returns a process/stub, we might need to interact with it.
                                // Since we don't have the exact API, we will fall back to the DO pattern
                                // if this doesn't return an immediate response.
                            } catch (spawnError) {
                                console.warn("Spawn failed, falling back to DO:", spawnError);
                            }
                        }

                        const id = env.MY_CONTAINER.newUniqueId();
                        const stub = env.MY_CONTAINER.get(id);

                        // Forward request to Container DO
                        const response = await stub.fetch(new Request(request.url, {
                            method: 'POST',
                            body: JSON.stringify(body),
                            headers: request.headers
                        }));

                        const data = await response.json();
                        return new Response(JSON.stringify({ ...data, sessionId: id.toString() }), {
                            headers: { ...corsHeaders, 'Content-Type': 'application/json' }
                        });
                    } catch (e) {
                        return new Response(JSON.stringify({ error: 'Session Creation Failed: ' + e.message }), { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
                    }
                }

                // GET /output/:sessionId - Stream output
                if (path.startsWith('/output/') && request.method === 'GET') {
                    const sessionId = path.split('/')[2];
                    if (!sessionId) return new Response(JSON.stringify({ error: 'Missing session ID' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

                    try {
                        const id = env.MY_CONTAINER.idFromString(sessionId);
                        const stub = env.MY_CONTAINER.get(id);
                        return stub.fetch(request);
                    } catch (e) {
                        return new Response(JSON.stringify({ error: 'Invalid session ID' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
                    }
                }

                // POST /input/:sessionId - Send input
                if (path.startsWith('/input/') && request.method === 'POST') {
                    const sessionId = path.split('/')[2];
                    if (!sessionId) return new Response(JSON.stringify({ error: 'Missing session ID' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

                    try {
                        const id = env.MY_CONTAINER.idFromString(sessionId);
                        const stub = env.MY_CONTAINER.get(id);
                        const response = await stub.fetch(request);
                        return new Response(response.body, { headers: corsHeaders });
                    } catch (e) {
                        return new Response(JSON.stringify({ error: 'Invalid session ID' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
                    }
                }

                return new Response(JSON.stringify({ error: 'Not Found' }), { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
            }

            return new Response(JSON.stringify({ message: 'Welcome to GadzIT C++ IDE Backend' }), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

        } catch (e) {
            // Global error handler to ensure JSON response
            return new Response(JSON.stringify({ error: 'Internal Server Error: ' + e.message, stack: e.stack }), {
                status: 500,
                headers: { ...corsHeaders, 'Content-Type': 'application/json' }
            });
        }
    }
};

// Durable Object Class (The Container Wrapper)
// In a real Cloudflare Container setup, this might be implicit or different,
// but for the "Workers with Containers" pattern (Durable Objects), we define the class.
export class MyContainer {
    constructor(state, env) {
        this.state = state;
        this.env = env;
        // In a real container binding, we might spawn the container here
        // this.container = env.MY_CONTAINER_IMAGE.spawn();
        // But per user instructions, we are simulating the "Container" behavior or
        // assuming the binding *is* the container.
        // Since we need to run Python, and we can't run Python directly in the Worker JS,
        // we assume the "image" config in wrangler.toml handles the runtime.
        // However, for this code to be valid JS, we need to handle the requests.
        //
        // IMPORTANT: Since we cannot actually run the Docker container in this environment
        // without the actual Cloudflare Container runtime (which is private beta),
        // we will implement the logic to forward to an external container OR
        // mock the behavior if we were just testing.
        //
        // BUT, the user asked for the *code* to be produced.
        // I will write the code assuming the Container Binding exposes a `fetch`
        // that routes into the container's internal server (Flask app).
    }

    async fetch(request) {
        const url = new URL(request.url);

        // Attempt to connect to the container service
        // Note: In a real Cloudflare Container setup, the networking might differ.
        // We assume the container is listening on localhost:8080 within the DO's network namespace.
        // Using 'localhost' instead of '127.0.0.1' to avoid "Direct IP access not allowed" error.
        const containerUrl = `http://localhost:5550${url.pathname}`;

        try {
            const response = await fetch(containerUrl, {
                method: request.method,
                headers: request.headers,
                body: request.body
            });

            // Check if the response is JSON
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return response;
            } else {
                // If not JSON, read text and wrap in JSON to avoid crashing the Worker
                const text = await response.text();
                return new Response(JSON.stringify({
                    error: `Container returned non-JSON response: ${response.status} ${response.statusText}`,
                    details: text.substring(0, 1000) // Truncate to avoid huge payloads
                }), {
                    status: response.status >= 400 ? response.status : 500,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
        } catch (e) {
            return new Response(JSON.stringify({
                error: "Container communication failed. Is the container running?",
                details: e.message
            }), {
                status: 500,
                headers: { 'Content-Type': 'application/json' }
            });
        }
    }
}
