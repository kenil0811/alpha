/**
 * Alpha's character: Bridge's Zazoo companion rig, ported wholesale from
 * platform/apps/web/src/app/avatar/zazoo/ (director + full painted-panda avatar). Same rig
 * Bridge's own desktop companion uses — breathing, blinking, saccades, mood-driven pose and
 * a `setTalking` mouth-flap while Alpha speaks — with the built-in prefers-reduced-motion
 * fallback to a static head (CompanionZazooFace -> ZazooCompact).
 */
import { useEffect, useMemo } from "react";
import { CompanionZazooFace } from "./zazoo/CompanionZazooFace";
import { ZazooDirector, type ZazooEmotion } from "./zazoo/director";

export type Mood = "idle" | "listening" | "thinking" | "talking" | "sorry";

const EMOTION: Record<Mood, ZazooEmotion> = {
  idle: "calm",
  listening: "listening",
  thinking: "thinking",
  talking: "happy",
  sorry: "concerned",
};

export function Character({ mood, size = 96 }: { mood: Mood; size?: number }) {
  const director = useMemo(() => new ZazooDirector(), []);
  useEffect(() => {
    director.perform({ emotion: EMOTION[mood], attention: mood === "idle" ? "cursor" : "user" });
    director.setTalking(mood === "talking");
  }, [director, mood]);
  return <CompanionZazooFace director={director} size={size} label={`Alpha is ${mood === "idle" ? "here" : mood}`} crop={false} />;
}
