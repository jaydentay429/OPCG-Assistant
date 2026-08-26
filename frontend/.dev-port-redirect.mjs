// Dev helper: bounce stale tabs on :3001 / :3002 to the real dev server on :3000.
import http from "node:http";

const TARGET_PORT = 3000;

for (const port of [3001, 3002]) {
  const server = http.createServer((req, res) => {
    const host = (req.headers.host || `localhost:${port}`).split(":")[0];
    res.writeHead(302, { Location: `http://${host}:${TARGET_PORT}${req.url || "/"}` });
    res.end();
  });
  server.on("error", (err) => console.error(`port ${port}: ${err.message}`));
  server.listen(port, () => console.log(`redirect ${port} -> ${TARGET_PORT}`));
}
