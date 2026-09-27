import type { Metadata } from "next";
import { PlayPausedNotice } from "@/components/PlayPausedNotice";
import { playPausedMetadata } from "@/lib/playPaused";

type Props = { params: Promise<{ slug?: string[] }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  return playPausedMetadata(slug);
}

export default function PlayPausedPage() {
  return <PlayPausedNotice />;
}
