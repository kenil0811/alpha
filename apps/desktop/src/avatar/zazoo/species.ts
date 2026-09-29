/**
 * Species — each character is a SMALL DELTA on the shared baseline, never a
 * new rig. Everybody keeps the same egg silhouette, suit, painted mitts,
 * standard mouth/brow parts and the full acting stack; a species only picks
 * its felt color and swaps the few features that carry identity.
 *
 * Feature primitives (the whole vocabulary):
 *   ears     cap (painted panda) · point · tall · bud · drop (floppy) ·
 *            side (low round, ape) · fin (fish) · none — sized by earSize
 *   eye      dark (panda gloss) · white sclera, customizable per animal:
 *            eyeScale, pupilSize, pupilAspect (>1 slit cat/snake, <1
 *            HORIZONTAL bar — sheep and goats really have those), eyeTilt
 *   nose     painted · tri · oval · nostrils (snout mound — rhino/pig/cow) ·
 *            beak (articulated: lower mandible drops with the jaw, so birds
 *            talk with it) · none
 *   horn     none · cone (rhino) · antlers (reindeer — females carry them,
 *            which is why Willow is a reindeer) · up (goat/cow/bison)
 *   back     none · quills · star · wool — silhouette accents behind body
 *   tail     stub · curl · puff · fan · bushy · paddle · finTail ·
 *            tentacles · tuft · none — always the ANIMAL's color: anatomy,
 *            not wardrobe
 *   flags    patches · whiskers · muzzle · crest
 *
 * The cast is Zootopia/Pixar-inspired, all-feminine, and stays on brand:
 * plush felt, muted palette, professional-minimal. Identity from the delta,
 * life from the shared rig.
 */

export interface ZazooSpecies {
  id: string;
  name: string;
  kind: string;
  ears: "cap" | "point" | "tall" | "bud" | "drop" | "side" | "fin" | "none";
  earSize?: number;
  eye: "dark" | "white";
  /** Sclera size multiplier (owl 1.45, bison 0.85). */
  eyeScale?: number;
  /** Pupil size multiplier (doe eyes 1.15, eagle 0.9). */
  pupilSize?: number;
  /** Pupil aspect: 1 round · >1 vertical slit · <1 horizontal bar. */
  pupilAspect?: number;
  /** Degrees; positive lifts the OUTER corners (fox/eagle), negative droops. */
  eyeTilt?: number;
  patches: boolean;
  whiskers: boolean;
  muzzle: boolean;
  crest?: boolean;
  nose: "painted" | "tri" | "oval" | "nostrils" | "beak" | "none";
  noseColor: string;
  horn: "none" | "cone" | "antlers" | "up";
  back: "none" | "quills" | "star" | "wool";
  earInner: string;
  /** A small felt cowlick on the crown. Off where headgear already lives
   * (crest/wool/quills) and for the sea creatures + snake. */
  hair?: boolean;
  tail: "stub" | "curl" | "puff" | "fan" | "bushy" | "paddle" | "finTail" | "tentacles" | "tuft" | "none";
  /** Default felt — a starting point, the fur swatches still apply. */
  body: string;
}

const base = {
  earSize: 1, eye: "white" as const, patches: false, whiskers: false,
  muzzle: false, crest: false, horn: "none" as const, back: "none" as const,
  hair: true,
};

export const SPECIES: ZazooSpecies[] = [
  { ...base, id: "zazoo", name: "Zazoo", kind: "panda", ears: "cap", eye: "dark", patches: true, nose: "painted", noseColor: "#1B1C21", earInner: "#2F3038", hair: false, tail: "none", body: "#FAF1E7" },
  { ...base, id: "mia", name: "Mia", kind: "cat", ears: "point", whiskers: true, eyeTilt: 6, pupilAspect: 1.6, nose: "tri", noseColor: "#E8899B", earInner: "#E9AEB6", tail: "curl", body: "#F0DFC2" },
  { ...base, id: "clover", name: "Clover", kind: "rabbit", ears: "tall", whiskers: true, eyeScale: 1.08, nose: "tri", noseColor: "#E39AA8", earInner: "#EDBCC6", tail: "puff", body: "#E6E8ED" },
  { ...base, id: "freya", name: "Freya", kind: "fox", ears: "point", whiskers: true, eyeTilt: 9, pupilSize: 0.95, nose: "tri", noseColor: "#463629", earInner: "#4A3A30", tail: "curl", body: "#D99A66" },
  { ...base, id: "bella", name: "Bella", kind: "bear", ears: "bud", muzzle: true, nose: "oval", noseColor: "#463629", earInner: "#A87C50", tail: "stub", body: "#C99C6E" },
  { ...base, id: "pippa", name: "Pippa", kind: "otter", ears: "bud", earSize: 0.85, whiskers: true, muzzle: true, nose: "oval", noseColor: "#4A3A30", earInner: "#96714C", tail: "curl", body: "#B98D64" },
  { ...base, id: "riya", name: "Riya", kind: "mongoose", ears: "bud", earSize: 0.8, whiskers: true, nose: "tri", noseColor: "#463629", earInner: "#A88E68", tail: "curl", body: "#C9AE84" },
  { ...base, id: "maple", name: "Maple", kind: "red panda", ears: "point", whiskers: true, nose: "oval", noseColor: "#3A3238", earInner: "#E3C3AC", tail: "curl", body: "#C97F5E" },
  { ...base, id: "willow", name: "Willow", kind: "reindeer", ears: "bud", horn: "antlers", eyeTilt: 5, pupilSize: 1.15, nose: "oval", noseColor: "#463629", earInner: "#A8845E", tail: "stub", body: "#C7A27E" },
  { ...base, id: "kiki", name: "Kiki", kind: "koala", ears: "bud", earSize: 1.35, nose: "oval", noseColor: "#3A3238", earInner: "#D6D9DE", tail: "stub", body: "#B8BCC4" },
  { ...base, id: "hazel", name: "Hazel", kind: "hamster", ears: "bud", earSize: 1.1, whiskers: true, nose: "tri", noseColor: "#E8899B", earInner: "#EFD9BE", tail: "stub", body: "#D9C4A8" },
  { ...base, id: "ruby", name: "Ruby", kind: "rhino", ears: "bud", earSize: 0.9, nose: "nostrils", noseColor: "#4A4550", horn: "cone", earInner: "#ABAFBC", tail: "stub", body: "#C7CBD6" },
  { ...base, id: "sasha", name: "Sasha", kind: "sloth", ears: "bud", earSize: 0.7, muzzle: true, eyeTilt: -8, pupilSize: 1.2, nose: "oval", noseColor: "#6B5B48", earInner: "#9C8E76", tail: "stub", body: "#B4A488" },
  { ...base, id: "nova", hair: false, name: "Nova", kind: "peafowl", ears: "none", crest: true, nose: "beak", noseColor: "#D9A24C", earInner: "#5E8C94", tail: "fan", body: "#5E8C94" },
  { ...base, id: "aria", name: "Aria", kind: "eagle", ears: "none", eyeTilt: 12, eyeScale: 1.05, pupilSize: 0.9, nose: "beak", noseColor: "#E0A93E", earInner: "#B0906A", tail: "stub", body: "#B0906A" },
  { ...base, id: "olive", name: "Olive", kind: "owl", ears: "point", earSize: 0.65, eyeScale: 1.45, pupilSize: 1.5, nose: "beak", noseColor: "#D9A24C", earInner: "#8C7E62", tail: "stub", body: "#A89878" },
  { ...base, id: "pearl", name: "Pearl", kind: "penguin", ears: "none", nose: "beak", noseColor: "#E0A93E", earInner: "#D8DCE4", tail: "stub", body: "#D8DCE4" },
  { ...base, id: "poppy", hair: false, name: "Poppy", kind: "porcupine", ears: "bud", earSize: 0.75, back: "quills", nose: "oval", noseColor: "#463629", earInner: "#96774E", tail: "stub", body: "#B4936A" },
  { ...base, id: "sage", hair: false, name: "Sage", kind: "snake", ears: "none", eyeScale: 1.1, pupilAspect: 2.4, nose: "none", noseColor: "#000", earInner: "#8FA379", tail: "none", body: "#8FA379" },
  { ...base, id: "coco", name: "Coco", kind: "chimpanzee", ears: "side", muzzle: true, nose: "nostrils", noseColor: "#5A4638", earInner: "#B49882", tail: "none", body: "#9C8672" },
  { ...base, id: "bree", name: "Bree", kind: "beaver", ears: "bud", earSize: 0.8, whiskers: true, nose: "tri", noseColor: "#463629", earInner: "#8A6844", tail: "paddle", body: "#A97C54" },
  { ...base, id: "suki", name: "Suki", kind: "squirrel", ears: "point", earSize: 0.75, whiskers: true, nose: "tri", noseColor: "#463629", earInner: "#D9B48F", tail: "bushy", body: "#C08552" },
  { ...base, id: "luna", hair: false, name: "Luna", kind: "jellyfish", ears: "none", eyeScale: 0.85, nose: "none", noseColor: "#000", earInner: "#B7A3C9", tail: "tentacles", body: "#B7A3C9" },
  { ...base, id: "stella", hair: false, name: "Stella", kind: "starfish", ears: "none", back: "star", nose: "none", noseColor: "#000", earInner: "#E0956B", tail: "none", body: "#E0956B" },
  { ...base, id: "bonnie", hair: false, name: "Bonnie", kind: "sheep", ears: "drop", earSize: 0.85, back: "wool", pupilAspect: 0.65, nose: "oval", noseColor: "#6B5B52", earInner: "#DCD2C4", tail: "puff", body: "#EDE6DA" },
  { ...base, id: "greta", name: "Greta", kind: "goat", ears: "drop", horn: "up", pupilAspect: 0.65, nose: "oval", noseColor: "#5C5048", earInner: "#C4B8A4", tail: "stub", body: "#D8CDBB" },
  { ...base, id: "daisy", name: "Daisy", kind: "cow", ears: "drop", horn: "up", eyeTilt: -3, pupilSize: 1.1, nose: "nostrils", noseColor: "#8A6258", earInner: "#D0BFA8", tail: "tuft", body: "#E3D9C8" },
  { ...base, id: "bess", name: "Bess", kind: "bison", ears: "bud", earSize: 0.7, horn: "up", eyeScale: 0.85, nose: "nostrils", noseColor: "#3E3028", earInner: "#5C4634", tail: "tuft", body: "#7A5C44" },
  { ...base, id: "rosie", name: "Rosie", kind: "pig", ears: "drop", earSize: 0.9, nose: "nostrils", noseColor: "#C97F86", earInner: "#EFC0BC", tail: "curl", body: "#E8B4A8" },
  { ...base, id: "coral", hair: false, name: "Coral", kind: "fish", ears: "fin", eyeScale: 1.1, nose: "none", noseColor: "#000", earInner: "#5E85A0", tail: "finTail", body: "#7FA3B8" },
];

export const DEFAULT_SPECIES = SPECIES[0];
