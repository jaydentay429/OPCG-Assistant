"use client";

import { attachChunkLoadRecovery } from "@/lib/chunkReload";
import { useEffect } from "react";

/** Listens for stale-chunk failures and reloads once. Renders nothing. */
export function ChunkLoadRecovery() {
  useEffect(() => attachChunkLoadRecovery(), []);
  return null;
}
