
export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        // CORS Headers
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders });
        }

        // API Routes
        if (url.pathname.startsWith('/api')) {
            const path = url.pathname.replace('/api', '');

            // POST /run - Start new session
            if (path === '/run' && request.method === 'POST') {
                try {
                    const body = await request.json();
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
                    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: corsHeaders });
                }
            }

            // GET /output/:sessionId - Stream output
            if (path.startsWith('/output/') && request.method === 'GET') {
                const sessionId = path.split('/')[2];
                if (!sessionId) return new Response('Missing session ID', { status: 400, headers: corsHeaders });

                try {
                    const id = env.MY_CONTAINER.idFromString(sessionId);
                    const stub = env.MY_CONTAINER.get(id);

                    // Forward to DO
                    return stub.fetch(request);
                } catch (e) {
                    return new Response('Invalid session ID', { status: 400, headers: corsHeaders });
                }
            }

            // POST /input/:sessionId - Send input
            if (path.startsWith('/input/') && request.method === 'POST') {
                const sessionId = path.split('/')[2];
                if (!sessionId) return new Response('Missing session ID', { status: 400, headers: corsHeaders });

                try {
                    const id = env.MY_CONTAINER.idFromString(sessionId);
                    const stub = env.MY_CONTAINER.get(id);

                    // Forward to DO
                    const response = await stub.fetch(request);
                    return new Response(response.body, { headers: corsHeaders });
                } catch (e) {
                    return new Response('Invalid session ID', { status: 400, headers: corsHeaders });
                }
            }

            return new Response('Not Found', { status: 404, headers: corsHeaders });
        }

        return new Response('Welcome to GadzIT C++ IDE Backend', { headers: corsHeaders });
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
        // In the "Workers with Containers" model, the DO *is* the container's entry point
        // or we proxy to it. 
        // If this class *is* the container definition in the config, then requests to this DO
        // are actually handled by the container if configured correctly.
        // 
        // However, usually you need to forward the request to the internal service.
        // Let's assume the container is running on localhost inside the DO sandbox 
        // or accessible via a binding.

        // For the purpose of this deliverable, I will assume the container is running 
        // the Flask app on port 8080 (or similar) and we proxy to it.
        // OR, if the `image` field in wrangler.toml does the magic, we might not even need this class
        // if the worker forwards directly. 
        // But the user asked for `env.MY_CONTAINER.spawn` which implies the Worker controls it.

        // Let's implement the logic to talk to the internal Flask app.
        // Since we can't easily "spawn" it in JS, we'll assume it's running.

        const url = new URL(request.url);

        // Rewrite URL to point to container service (localhost inside the DO?)
        // This is speculative as the API is beta.
        // A common pattern is `fetch('http://localhost:8080' + path)`

        try {
            // We'll use a hypothetical internal fetch to the container
            // In reality, this might need adjustment based on the specific beta API.
            const containerUrl = `http://127.0.0.1:8080${url.pathname}`;

            // Forward the request to the Python Flask app running in the container
            const response = await fetch(containerUrl, {
                method: request.method,
                headers: request.headers,
                body: request.body
            });

            return response;
        } catch (e) {
            // Fallback/Mock for demonstration if container isn't actually running in this env
            return new Response(JSON.stringify({ error: "Container communication failed: " + e.message }), { status: 500 });
        }
    }
}
