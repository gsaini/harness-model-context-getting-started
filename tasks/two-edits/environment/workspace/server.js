// Minimal API server. Listens on port 3000 by default.
const express = require("express");
const PORT = 3000;
const TIMEOUT_MS = 3000;

const app = express();
app.get("/health", (req, res) => res.json({ ok: true }));
app.listen(PORT, () => console.log("listening on " + PORT));
