/**
 * Zazoo Animation Director — translates intent into a continuous pose stream.
 * Renderer-agnostic: emits a plain numeric Frame each tick that any renderer
 * (SVG today, canvas/3D later) maps onto a rig. The LLM/agent plane talks to
 * this via `perform()`; it never drives individual features directly.
 *
 * TWO INDEPENDENT CHANNELS (they compose, they are not alternatives):
 *   emotion — how Zazoo FEELS  (face, brows, cheeks, breath rhythm)
 *   action  — what Zazoo is DOING (whole-body activity: meditate/sneak/hide)
 * Zazoo can be `happy` while `meditating`, or `concerned` while `hiding`.
 * Layering: CALM base ← emotion overrides ← action overrides (body wins).
 *
 * Acting model (Pixar canon, see docs/raw/zazoo-companion-avatar-roadmap):
 * no fixed clips — spring-blended pose targets + autonomous behaviors
 * (breath/blink/saccade/whisker-float/ear-twitch) + one-shot gestures with
 * anticipation and squash-and-stretch. Secondary motion (whiskers, ears,
 * spectacles) lags primary motion for follow-through.
 */

import { MOUTH_SHAPES, BROW_SHAPES, type MouthShape, type BrowShape } from "./parts";

export type ZazooEmotion =
  | "calm"
  | "curious"
  | "thinking"
  | "listening"
  | "happy"
  | "proud"
  | "unsure"
  | "concerned"
  | "comforting"
  | "celebrating"
  | "sleepy";

/** Whole-body activity — orthogonal to emotion. */
export type ZazooAction = "idle" | "meditating" | "sneaking" | "hiding";

/** Contract the agent plane uses to request a performance. */
export interface ZazooPerformance {
  /** How Zazoo feels. Omit to leave the current emotion untouched. */
  emotion?: ZazooEmotion;
  /** What Zazoo is doing. Omit to leave the current action untouched. */
  action?: ZazooAction;
  /** 0..1 — scales smile/cheek warmth + cheek color temperature. */
  warmth?: number;
  /** 0..1 — posture openness; low confidence softens gaze + tilt. */
  confidence?: number;
  /** 0..1 — movement speed, breath rate, saccade frequency. */
  energy?: number;
  attention?: "user" | "cursor" | "away";
  intent?: string;
  /** Seconds before reverting whatever this call set back to its default. */
  duration?: number;
}

/** Springed pose parameters (targets set by emotion + action presets). */
interface Pose {
  eyeOpen: number; // 0 closed .. 1 normal .. 1.15 wide
  pupilScale: number;
  browRaise: number; // -1 lowered .. 1 raised (also lengthens the brow)
  browSorrow: number; // 0..1 inner-raise (worry)
  browFurrow: number; // 0..1 inner-lower (focus) — also shortens the brow
  /**
   * Extra jaw travel on top of whichever standard mouth part is showing —
   * this is the LIVE part of the mouth (it rides the breath), not the shape
   * itself. The shape comes from the artist's sheet via `mouth` below.
   */
  mouthOpen: number;
  /** Size of the mouth part relative to how the sheet draws it. */
  mouthScale: number;
  earL: number; // deg, + = perked
  earR: number;
  earScale: number; // 1 = rest; listening exaggerates (mild)
  headTilt: number; // deg
  headDrop: number; // px face-group lowering
  cheek: number; // 0..1 blush opacity
  cheekWarm: number; // 0..1 blush color temperature (pale pink → warm coral)
  cheekPuff: number; // 0..1 cheek lift/puff scale
  whiskerDroop: number; // 0..1
  whiskerFloat: number; // 0..1 airy idle sway amplitude
  tailCurl: number; // 0..1 (oval tail rock bias)
  bodyLean: number; // deg, + = toward user
  posture: number; // 0 slouch .. 1 upright-proud
  pawChest: number; // 0..1 paw-over-chest (comforting)
  pawMeditate: number; // 0..1 both paws meet at front, palms up
  /**
   * HAND CHOREOGRAPHY — at rest the paws sit low and quiet against the suit
   * (the reference art is a clean egg; hands that are always mid-gesture read
   * as noise). Each channel raises them into ONE meaningful stage position,
   * so a gesture is an event, not a decoration. Ported from the v3 photo rig
   * (c3aa693), whose rule was: the hand goes where the work is.
   */
  pawChin: number; // 0..1 right paw up to the chin (thinking / curious)
  pawFold: number; // 0..1 both paws meet at the chest, folded (listening/proud)
  pawOpen: number; // 0..1 palms turned out toward the user (comforting/offering)
  pawUp: number; // 0..1 sustained both-arms-raised (celebrating)
  pawDroop: number; // 0..1 heavy arms sliding down and out (sleepy)
  /**
   * -1 STRETCH (tall + narrow, lifted/proud/airborne) .. 0 rest .. 1 SQUASH
   * (short + wide, heavy/sleepy/crouched). Bipolar on purpose: Pixar's first
   * principle needs both halves, and volume is preserved in the renderer so
   * either direction still reads as the same amount of panda.
   */
  squash: number;
  hide: number; // 0..1 roll-and-wrap into a compact cloth bundle
  levitate: number; // 0..1 meditation float
  gazeBiasX: number; // -1..1 emotion-driven gaze offset
  gazeBiasY: number;
}

/**
 * Non-springed behavior settings — including which of the artist's standard
 * parts is showing. Shapes are picked, not springed: the renderer crossfades
 * between the chosen part and the previous one, so a switch is still smooth
 * without the director having to interpolate geometry it does not own.
 */
interface Behavior {
  mouth: MouthShape;
  brow: BrowShape;
  breathRate: number; // Hz — varies with emotion; actions may override
  breathDepth: number; // 0..1.2
  blinkEvery: number; // mean seconds between blinks
  blinkSpeed: number; // 1 = normal, <1 slower (sleepy)
  saccadeAmp: number; // 0..1
  tailWag: number; // 0..1 oval-tail rock intensity
  nod: number; // 0..1 slow attentive nodding
  giggle: number; // 0..1 petting wiggle (Zazoo speaks/giggles — never purrs)
  creep: number; // 0..1 sneak tip-toe bob
  tap: number; // 0..1 chin-paw finger tap while thinking
  fidget: number; // 0..1 folded paws rub against each other (unsure)
}

/** What the renderer consumes every frame. */
export interface ZazooFrame extends Pose {
  blink: number;
  breath: number; // -1..1 oscillation at the current rhythm
  gazeX: number;
  gazeY: number;
  /**
   * The head's own, LAGGED copy of the gaze. Lasseter: the eyes lead every
   * action — a dart is instant, the head follows because it decided to. The
   * renderer points pupils at gazeX/Y and the face at headGazeX/Y; the gap
   * between them is the visible thought.
   */
  headGazeX: number;
  headGazeY: number;
  hopY: number; // px vertical offset (gestures + levitate + creep)
  wiggle: number; // deg root rotation (giggle)
  pawLift: number; // 0..1 right paw to spectacles
  armsUp: number; // 0..1 both paws celebration
  specJiggle: number;
  tailWagPhase: number;
  wagAmount: number;
  nodY: number;
  whiskerSway: number; // deg — whiskers floating in air
  sparkle: number;
  zzz: number;
  /** 0..1 syllable envelope while speaking — rides on top of mouthOpen. */
  talk: number;
  /** wave gesture: envelope + its oscillation, right paw greeting. */
  wave: number;
  waveOsc: number;
  /** px — chin-paw tap offset (thinking); already time-shaped. */
  pawTap: number;
  /** px — folded-paw rub offset (unsure); already time-shaped. */
  fidgetX: number;
  /**
   * Blend weights over MOUTH_SHAPES / BROW_SHAPES, summing to 1. The renderer
   * mixes the traced loops by these, which is how a switch between two of the
   * artist's parts becomes a continuous morph instead of a cut.
   */
  mouthW: readonly number[];
  browW: readonly number[];
}

const CALM: Pose = {
  eyeOpen: 0.9, pupilScale: 1, browRaise: 0, browSorrow: 0, browFurrow: 0,
  mouthOpen: 0, mouthScale: 1, earL: 0, earR: 0, earScale: 1,
  headTilt: 0, headDrop: 0, cheek: 0.45, cheekWarm: 0.4, cheekPuff: 0.2,
  whiskerDroop: 0.1, whiskerFloat: 0.6, tailCurl: 0.3, bodyLean: 0,
  posture: 0.5, pawChest: 0, pawMeditate: 0,
  pawChin: 0, pawFold: 0, pawOpen: 0, pawUp: 0, pawDroop: 0,
  squash: 0, hide: 0,
  levitate: 0, gazeBiasX: 0, gazeBiasY: 0,
};
/** Global breath damping — see the note at the application site. */
const BREATH_RATE_DAMP = 0.55;
const BREATH_DEPTH_DAMP = 0.5;

const CALM_B: Behavior = {
  mouth: "smileTwin", brow: "arch",
  breathRate: 0.22, breathDepth: 0.6, blinkEvery: 4.2, blinkSpeed: 1,
  saccadeAmp: 0.5, tailWag: 0.08, nod: 0, giggle: 0, creep: 0,
  tap: 0, fidget: 0,
};

/**
 * EMOTION layer — face, brows, cheeks, breath rhythm.
 *
 * Every emotion picks a MOUTH PART and a BROW PART from the artist's standard
 * sheet, and states a body SQUASH bias. Those carry most of the read at a
 * glance: a mouth that only changed its smile depth, on a body that never
 * changed volume, is what makes a rig look like a decal instead of a character.
 */
const EMOTIONS: Record<ZazooEmotion, [Partial<Pose>, Partial<Behavior>]> = {
  calm: [{}, {}],
  curious: [
    // lips part on the unspoken question; a paw drifts halfway to the chin
    { eyeOpen: 1.12, pupilScale: 1.18, browRaise: 0.75, headTilt: 9, earL: 8, earR: 8, earScale: 1.08, mouthScale: 0.42, squash: -0.14, cheekPuff: 0.3, whiskerFloat: 0.9, pawChin: 0.55 },
    { mouth: "openRound", brow: "perk", blinkEvery: 7, saccadeAmp: 0.25, breathRate: 0.3, breathDepth: 0.5 },
  ],
  thinking: [
    // small and shut — the mouth gets out of the way while the brow works;
    // the paw is fully at the chin, tapping (the tap is the visible thought)
    { eyeOpen: 0.78, browRaise: 0.2, browFurrow: 0.6, headTilt: -6, mouthScale: 0.78, squash: 0.08, gazeBiasY: -0.8, gazeBiasX: 0.35, earL: 3, earR: -2, cheekPuff: 0.1, pawChin: 1 },
    { mouth: "smile", brow: "wave", blinkEvery: 5.5, saccadeAmp: 0.3, breathRate: 0.16, breathDepth: 0.8, tap: 1 },
  ],
  listening: [
    // Ears enlarge — mild Pixar exaggeration: the feature doing the work grows.
    // Paws fold quietly at the chest: full attention, nothing else moving.
    { eyeOpen: 0.98, earL: 12, earR: 12, earScale: 1.28, mouthOpen: 0.08, squash: -0.06, headTilt: 3, posture: 0.65, whiskerFloat: 0.3, browRaise: 0.25, pawFold: 0.85 },
    { mouth: "smileTwin", brow: "arch", blinkEvery: 5, saccadeAmp: 0.15, nod: 0.6, breathRate: 0.2, breathDepth: 0.5 },
  ],
  happy: [
    // greeting-warm; perform() adds a one-shot wave so the joy has a gesture
    { eyeOpen: 0.66, mouthScale: 1.05, mouthOpen: 0.12, squash: -0.16, cheek: 0.9, cheekWarm: 0.85, cheekPuff: 0.8, earL: 4, earR: 4, tailCurl: 0.5, whiskerFloat: 1, browRaise: 0.4 },
    { mouth: "arch", brow: "perk", tailWag: 0.45, breathRate: 0.28, breathDepth: 0.55, blinkEvery: 4.5 },
  ],
  proud: [
    // chest up, drawn tall, paws folded high like hands on lapels
    { eyeOpen: 0.75, mouthScale: 0.95, squash: -0.3, posture: 1, headTilt: -2, cheek: 0.55, cheekWarm: 0.6, cheekPuff: 0.5, earL: 6, earR: 6, browRaise: 0.3, pawFold: 0.7 },
    { mouth: "arch", brow: "perk", breathRate: 0.18, breathDepth: 0.9, blinkEvery: 5 },
  ],
  unsure: [
    // paws find each other and rub — the classic nervous tell
    { eyeOpen: 0.8, browSorrow: 0.7, headTilt: -5, headDrop: 4, mouthScale: 0.88, squash: 0.14, tailCurl: 0.85, earL: -6, earR: -8, gazeBiasX: -0.5, cheek: 0.5, cheekWarm: 0.3, cheekPuff: 0.15, pawFold: 0.9 },
    { mouth: "wavy", brow: "wave", blinkEvery: 2.6, saccadeAmp: 0.7, breathRate: 0.33, breathDepth: 0.45, fidget: 1 },
  ],
  concerned: [
    { eyeOpen: 0.92, browSorrow: 1, squash: 0.1, bodyLean: 4, cheek: 0.15, cheekWarm: 0.1, earL: -4, earR: -4, whiskerDroop: 0.5, whiskerFloat: 0.2, pawFold: 1 },
    { mouth: "wavy", brow: "wave", blinkEvery: 4, breathRate: 0.27, breathDepth: 0.5, saccadeAmp: 0.2 },
  ],
  comforting: [
    // palms open toward the user — offering, not holding back
    { eyeOpen: 0.6, squash: 0.1, cheek: 0.6, cheekWarm: 0.55, cheekPuff: 0.5, pawOpen: 1, headTilt: 4, earL: -2, earR: -2, browSorrow: 0.25 },
    { mouth: "smile", brow: "arch", blinkEvery: 6, blinkSpeed: 0.45, breathRate: 0.13, breathDepth: 1.1, nod: 0.3 },
  ],
  celebrating: [
    // arms stay up between hops — celebration is a held posture, not a blip
    { eyeOpen: 1.08, mouthScale: 0.92, mouthOpen: 0.35, squash: -0.34, cheek: 1, cheekWarm: 1, cheekPuff: 1, earL: 12, earR: 12, earScale: 1.1, tailCurl: 0.6, whiskerFloat: 1, browRaise: 0.9, pawUp: 0.65 },
    { mouth: "openWide", brow: "perk", tailWag: 1, breathRate: 0.42, breathDepth: 0.4, blinkEvery: 5, saccadeAmp: 0.3 },
  ],
  sleepy: [
    // slack jaw, and the whole panda settles into itself under its own weight
    { eyeOpen: 0.3, mouthScale: 0.4, mouthOpen: 0.25, squash: 0.3, earL: -12, earR: -12, earScale: 0.94, headTilt: 5, headDrop: 5, whiskerDroop: 0.8, whiskerFloat: 0.15, tailCurl: 0.7, cheek: 0.35, cheekWarm: 0.3, browRaise: -0.3, pawDroop: 1 },
    { mouth: "openTall", brow: "wave", blinkEvery: 3, blinkSpeed: 0.3, breathRate: 0.1, breathDepth: 1.2, saccadeAmp: 0.1 },
  ],
};

/** ACTION layer — whole-body activity; overrides the emotion's body params. */
const ACTIONS: Record<ZazooAction, [Partial<Pose>, Partial<Behavior>]> = {
  idle: [{}, {}],
  meditating: [
    // eyes FULLY closed — the renderer draws the lid arc once eyeOpen hits 0
    { eyeOpen: 0, pawMeditate: 1, levitate: 1, posture: 0.8, earL: 2, earR: 2, whiskerFloat: 0.8, headTilt: 0, headDrop: 0 },
    { breathRate: 0.07, breathDepth: 1.2, blinkEvery: 999, saccadeAmp: 0, tailWag: 0 },
  ],
  sneaking: [
    { squash: 0.7, bodyLean: 7, earL: 14, earR: 14, earScale: 1.15, pupilScale: 1.1, whiskerFloat: 0.2, posture: 0.2 },
    { saccadeAmp: 1, breathRate: 0.35, breathDepth: 0.3, creep: 1, tailWag: 0 },
  ],
  hiding: [
    { hide: 1, squash: 0.4 },
    { breathRate: 0.3, breathDepth: 0.2, blinkEvery: 999, saccadeAmp: 0, tailWag: 0 },
  ],
};

type GestureName = "specAdjust" | "hop" | "nodOnce" | "yawn" | "tiltIn" | "earFlick" | "wave";
interface Gesture { name: GestureName; start: number; dur: number }

const POSE_KEYS = Object.keys(CALM) as (keyof Pose)[];

/**
 * Move a weight vector toward one-hot on `i`, in place. Because every weight
 * steps by the same fraction toward its target, the sum is preserved at 1 —
 * so the blend it drives is always a valid convex mix, mid-morph included.
 */
function fadeTo(w: number[], i: number, rate: number) {
  const k = Math.max(0, Math.min(1, rate));
  for (let j = 0; j < w.length; j++) w[j] += ((j === i ? 1 : 0) - w[j]) * k;
}

function spring(x: number, v: number, target: number, dt: number, hz: number): [number, number] {
  const w = 2 * Math.PI * hz;
  const a = w * w * (target - x) - 2 * w * v;
  v += a * dt;
  x += v * dt;
  return [x, v];
}

export class ZazooDirector {
  emotion: ZazooEmotion = "calm";
  action: ZazooAction = "idle";
  private warmth = 0.7;
  private confidence = 0.7;
  private energy = 0.5;
  private attention: "user" | "cursor" | "away" = "cursor";
  private revertAt: number | null = null;
  private revertEmotion = false;
  private revertAction = false;

  private pose: Pose = { ...CALM };
  private vel: Record<keyof Pose, number> = Object.fromEntries(POSE_KEYS.map((k) => [k, 0])) as Record<keyof Pose, number>;

  private petting = false;
  private talking = false;
  private cursor: { x: number; y: number } | null = null;

  // one-hot at rest, mid-morph in between
  private mouthW = MOUTH_SHAPES.map((s) => (s === CALM_B.mouth ? 1 : 0));
  private browW = BROW_SHAPES.map((s) => (s === CALM_B.brow ? 1 : 0));

  private nextBlink = 1.5;
  private blinkT = -1;
  private doubleBlink = false;
  private nextSaccade = 0.8;
  private sacX = 0; private sacY = 0;
  private hgX = 0; private hgY = 0; // head's lagged gaze
  private nextEarTwitch = 6;
  private earTwitchT = -1;
  private nextIdleGesture = 12;
  private breathPhase = 0;
  private wagPhase = 0;
  private gestures: Gesture[] = [];
  private specJiggleV = 0; private specJiggleX = 0;
  private last = -1;

  perform(p: ZazooPerformance, now = performance.now() / 1000) {
    if (p.emotion) this.emotion = p.emotion;
    if (p.action) this.action = p.action;
    if (p.warmth !== undefined) this.warmth = p.warmth;
    if (p.confidence !== undefined) this.confidence = p.confidence;
    if (p.energy !== undefined) this.energy = p.energy;
    if (p.attention) this.attention = p.attention;

    if (p.duration) {
      this.revertAt = now + p.duration;
      this.revertEmotion = !!p.emotion;
      this.revertAction = !!p.action;
    } else {
      this.revertAt = null;
    }

    // Anticipation: every shift in state lands with a physical beat. Kicking
    // the squash SPRING (not the pose) means the body dips and rebounds on its
    // own timing, so no two transitions read identically.
    this.vel.squash += 5.5;
    this.specJiggleV += 14; // spectacles settle on every shift
    // A blink on the turn. Animators cut on a blink for the same reason
    // editors cut on a blink: it hides the change of expression and makes the
    // new one feel arrived-at rather than swapped in.
    if (p.emotion && this.blinkT < 0) this.nextBlink = Math.min(this.nextBlink, 0.06);
    if (p.emotion === "thinking" || p.emotion === "unsure") this.trigger("specAdjust", now, 0.4);
    if (p.emotion === "celebrating") this.trigger("hop", now);
    if (p.emotion === "proud") this.trigger("nodOnce", now, 0.3);
    if (p.emotion === "curious") this.trigger("tiltIn", now);
    if (p.emotion === "happy" || p.emotion === "comforting") this.trigger("earFlick", now);
    // joy greets: the arrival of "happy" is a one-shot wave, so the feeling
    // has a gesture and the gesture has a reason
    if (p.emotion === "happy") this.trigger("wave", now, 0.15);
    if (p.emotion === "unsure") this.doubleBlink = true;
  }

  setEmotion(e: ZazooEmotion) { this.perform({ emotion: e }); }
  setAction(a: ZazooAction) { this.perform({ action: a }); }
  /** Capture tell: close both eyes once without changing the companion's mood. */
  triggerBlink(now = performance.now() / 1000) {
    this.blinkT = 0;
    this.nextBlink = 4.2;
    this.last = this.last < 0 ? now : this.last;
  }
  setPetting(on: boolean) { this.petting = on; }
  setTalking(on: boolean) { this.talking = on; }
  setCursor(c: { x: number; y: number } | null) { this.cursor = c; }

  /** One-shot greeting — also fires on its own when `happy` arrives. */
  waveHello(now = performance.now() / 1000) { this.trigger("wave", now); }

  private trigger(name: GestureName, now: number, delay = 0) {
    const dur = { specAdjust: 1.6, hop: 1.3, nodOnce: 1.2, yawn: 2.2, tiltIn: 1.1, earFlick: 0.7, wave: 2.4 }[name];
    this.gestures.push({ name, start: now + delay, dur });
  }

  tick(now: number): ZazooFrame {
    if (this.last < 0) this.last = now;
    const dt = Math.min(0.05, now - this.last);
    this.last = now;

    if (this.revertAt !== null && now >= this.revertAt) {
      this.revertAt = null;
      if (this.revertEmotion) this.emotion = "calm";
      if (this.revertAction) this.action = "idle";
    }

    // layer: base ← emotion ← action (body activity wins over felt state)
    const [ep, eb] = EMOTIONS[this.emotion];
    const [ap, ab] = ACTIONS[this.action];
    const target: Pose = { ...CALM, ...ep, ...ap };
    const beh: Behavior = { ...CALM_B, ...eb, ...ab };

    target.mouthScale *= 1 + (this.warmth - 0.5) * 0.24;
    target.cheek = Math.min(1, target.cheek + (this.warmth - 0.5) * 0.4);
    target.cheekWarm = Math.min(1, target.cheekWarm + (this.warmth - 0.5) * 0.3);
    target.posture += (this.confidence - 0.5) * 0.4;
    target.headDrop += (0.5 - this.confidence) * 3;
    beh.breathRate *= 0.75 + this.energy * 0.6;
    // Breath is the "is this thing alive" tell, and a tell only works while
    // you have to look for it. Every emotion's rate/depth was tuned against a
    // 340px lab rig; at real sizes it read as panting. Damped globally so the
    // EMOTIONAL differences between calm and excited survive intact — only the
    // absolute amount comes down (user report 2026-08-17: "breathing too fast,
    // not subtly").
    beh.breathRate *= BREATH_RATE_DAMP;
    beh.breathDepth *= BREATH_DEPTH_DAMP;
    beh.saccadeAmp *= 0.6 + this.energy * 0.8;

    let giggle = beh.giggle;
    if (this.petting && this.action !== "hiding") {
      target.eyeOpen = 0.06;
      target.mouthOpen = 0.3;
      target.mouthScale = 0.8;
      target.squash = 0.2;
      target.cheek = 1; target.cheekWarm = 0.95; target.cheekPuff = 1;
      target.earL = -4; target.earR = -4;
      giggle = 1; // Zazoo giggles — it speaks, it does not purr
    }

    // Speaking: a two-sine syllable envelope (never phase-locks into a metronome)
    // opens the jaw on top of whatever part is showing. The shape crossfade
    // below also leans toward the round open part while a syllable peaks, so
    // chatter alternates between the emotion's mouth and an open one.
    let talk = 0;
    if (this.talking && this.action !== "hiding" && !this.petting) {
      talk = Math.max(0, Math.sin(now * 9.1) * 0.62 + Math.sin(now * 13.7) * 0.48);
      target.mouthOpen = Math.max(target.mouthOpen, 0.12 + talk * 0.5);
    }

    const speed = 0.8 + this.energy * 0.8;
    for (const k of POSE_KEYS) {
      // squash and the mouth are the fast channels — a body beat that settles
      // as slowly as a posture change reads as drift, not as weight. Paws are
      // quick too: a gesture that oozes into place stops being a gesture.
      const hz =
        (k === "eyeOpen" ? 4 : k === "squash" ? 2.4 : k.startsWith("mouth") ? 3 : k === "hide" ? 1.6 : k.startsWith("gaze") ? 2.5 : k.startsWith("paw") ? 2.1 : 1.4) * speed;
      const [x, v] = spring(this.pose[k], this.vel[k], target[k], dt, hz);
      this.pose[k] = x; this.vel[k] = v;
    }

    // breathing — frequency + depth are emotional signals in their own right
    this.breathPhase += dt * beh.breathRate * 2 * Math.PI;
    const breath = Math.sin(this.breathPhase) * beh.breathDepth;

    let blink = 0;
    if (this.blinkT >= 0) {
      this.blinkT += dt * 6.5 * beh.blinkSpeed;
      blink = Math.sin(Math.min(Math.PI, this.blinkT * Math.PI));
      if (this.blinkT >= 1) {
        this.blinkT = -1;
        if (this.doubleBlink) { this.doubleBlink = false; this.nextBlink = 0.18; }
      }
    } else {
      this.nextBlink -= dt;
      if (this.nextBlink <= 0) {
        this.blinkT = 0;
        this.nextBlink = beh.blinkEvery * (0.6 + Math.random() * 0.8);
      }
    }

    this.nextSaccade -= dt;
    if (this.nextSaccade <= 0) {
      this.sacX = (Math.random() - 0.5) * 0.5 * beh.saccadeAmp;
      this.sacY = (Math.random() - 0.5) * 0.35 * beh.saccadeAmp;
      this.nextSaccade = (beh.creep ? 0.25 : 0.4) + Math.random() * 1.8;
    }
    let gx = this.pose.gazeBiasX + this.sacX;
    let gy = this.pose.gazeBiasY + this.sacY;
    if (this.attention === "cursor" && this.cursor && !this.petting) {
      gx += this.cursor.x * 0.8;
      gy += this.cursor.y * 0.8;
    } else if (this.attention === "away") {
      gx += 0.7;
    }
    gx = Math.max(-1, Math.min(1, gx));
    gy = Math.max(-1, Math.min(1, gy));
    // eyes lead, head follows — the head chases the gaze at ~1/4 second, so
    // a glance stays a glance and only a HELD look turns the whole face
    const chase = Math.min(1, dt * 3.6);
    this.hgX += (gx - this.hgX) * chase;
    this.hgY += (gy - this.hgY) * chase;

    let earTwitch = 0;
    if (this.earTwitchT >= 0) {
      this.earTwitchT += dt * 8;
      earTwitch = Math.sin(Math.min(Math.PI, this.earTwitchT * Math.PI)) * 9;
      if (this.earTwitchT >= 1) this.earTwitchT = -1;
    } else {
      this.nextEarTwitch -= dt;
      if (this.nextEarTwitch <= 0) { this.earTwitchT = 0; this.nextEarTwitch = 5 + Math.random() * 14; }
    }

    this.nextIdleGesture -= dt;
    if (this.nextIdleGesture <= 0) {
      if (this.emotion === "sleepy" && this.action === "idle") this.trigger("yawn", now);
      this.nextIdleGesture = 10 + Math.random() * 15;
    }

    // gestures — hop carries anticipation (crouch) then squash-and-stretch
    let hopY = 0, pawLift = 0, armsUp = 0, nodOnceY = 0, yawnOpen = 0, hopSquash = 0;
    let leanIn = 0, flick = 0, wave = 0, waveOsc = 0;
    this.gestures = this.gestures.filter((g) => now < g.start + g.dur);
    for (const g of this.gestures) {
      if (now < g.start) continue;
      const p = (now - g.start) / g.dur;
      const env = Math.sin(Math.PI * Math.min(1, p));
      if (g.name === "hop") {
        if (p < 0.18) {
          hopSquash = Math.sin((p / 0.18) * Math.PI) * 0.5; // anticipation crouch
        } else {
          const q = (p - 0.18) / 0.82;
          hopY = -Math.abs(Math.sin(q * Math.PI * 2)) * 18 * Math.sin(Math.PI * q);
          hopSquash = -0.25 * Math.sin(q * Math.PI * 2); // stretch in air
          armsUp = Math.sin(Math.PI * q);
        }
      } else if (g.name === "specAdjust") {
        pawLift = env;
        if (p > 0.45 && p < 0.6) this.specJiggleV += dt * 220;
      } else if (g.name === "nodOnce") {
        nodOnceY = Math.sin(p * Math.PI * 2) * 3.5 * env;
      } else if (g.name === "yawn") {
        yawnOpen = env;
      } else if (g.name === "tiltIn") {
        // curiosity leans in and then settles back — the lean IS the question
        leanIn = env;
      } else if (g.name === "earFlick") {
        flick = Math.sin(p * Math.PI * 2) * env;
      } else if (g.name === "wave") {
        // the envelope raises the paw; the oscillation is the wave itself
        wave = env;
        waveOsc = Math.sin(p * Math.PI * 6);
      }
    }

    // Shape crossfade. Weights move toward one-hot on the chosen part at a
    // rate that scales with energy, so an excited switch snaps and a sleepy
    // one drifts. A yawn borrows the tall-open part on top of whatever is
    // showing, which is why it can interrupt any expression cleanly.
    const mouthTarget = this.petting && this.action !== "hiding" ? "openWide" : beh.mouth;
    fadeTo(this.mouthW, MOUTH_SHAPES.indexOf(mouthTarget), dt * 8 * speed);
    if (yawnOpen > 0.01) fadeTo(this.mouthW, MOUTH_SHAPES.indexOf("openTall"), yawnOpen * 0.5);
    // chatter: each syllable pulls the shape toward the round open part and
    // releases it back to the emotion's own mouth between syllables
    if (talk > 0.05) fadeTo(this.mouthW, MOUTH_SHAPES.indexOf("openRound"), Math.min(1, dt * 14) * talk);
    fadeTo(this.browW, BROW_SHAPES.indexOf(beh.brow), dt * 8 * speed);

    const [jx, jv] = spring(this.specJiggleX, this.specJiggleV, 0, dt, 3.2);
    this.specJiggleX = jx; this.specJiggleV = jv;

    this.wagPhase += dt * (2 + beh.tailWag * 9);
    const nodY = beh.nod * Math.sin(now * 1.6) * 2.2 + nodOnceY;
    const creepY = beh.creep * Math.sin(now * 3.2) * 2;
    const levitateY = this.pose.levitate * (Math.sin(now * 0.9) * 3 - 5);
    const wiggle = giggle * Math.sin(now * 16) * 2.4;

    // whiskers floating in air — breath-coupled + their own slow sway
    const whiskerSway =
      this.pose.whiskerFloat * (Math.sin(now * 1.4) * 2.4 + Math.sin(now * 0.53 + 1.7) * 1.4) +
      breath * 0.8;

    return {
      ...this.pose,
      eyeOpen: Math.max(0, this.pose.eyeOpen * (1 - blink) - yawnOpen * 0.6),
      // A parted mouth never holds still: the jaw rides the breath, so idling
      // reads as alive rather than as a paused frame.
      mouthOpen: Math.max(
        0,
        Math.min(1, this.pose.mouthOpen * (1 + breath * 0.22) + yawnOpen + giggle * 0.2),
      ),
      squash: Math.max(-1, Math.min(1, this.pose.squash + hopSquash + breath * 0.03)),
      blink,
      breath,
      gazeX: gx,
      gazeY: gy,
      headGazeX: this.hgX,
      headGazeY: this.hgY,
      hopY: hopY + creepY + levitateY,
      wiggle,
      pawLift,
      armsUp,
      specJiggle: this.specJiggleX,
      tailWagPhase: this.wagPhase,
      wagAmount: beh.tailWag,
      nodY,
      whiskerSway,
      earL: this.pose.earL + earTwitch + flick * 10,
      earR: this.pose.earR - flick * 7, // the two ears never flick together
      // idle weight shift — two slow incommensurate sines, so the body never
      // sits mathematically still and never visibly repeats. Nothing alive
      // holds a pose to the pixel; this is the difference between a character
      // at rest and a paused frame.
      headTilt: this.pose.headTilt + leanIn * 4 + Math.sin(now * 0.31 + 1.3) * 0.5,
      bodyLean: this.pose.bodyLean + leanIn * 5 + Math.sin(now * 0.23) * 0.45,
      sparkle: this.emotion === "celebrating" || this.emotion === "curious" ? 1 : 0,
      zzz: this.emotion === "sleepy" ? 1 : 0,
      talk,
      wave,
      waveOsc,
      // time-shaped here so the renderer stays dumb: the tap only exists
      // while the paw is actually at the chin, the rub only while folded
      pawTap: beh.tap * this.pose.pawChin * Math.max(0, Math.sin(now * 5.2)) * 2.2,
      fidgetX: beh.fidget * this.pose.pawFold * Math.sin(now * 7.3) * 1.6,
      mouthW: this.mouthW,
      browW: this.browW,
    };
  }
}

export const ZAZOO_EMOTIONS: ZazooEmotion[] = [
  "calm", "curious", "thinking", "listening", "happy", "proud",
  "unsure", "concerned", "comforting", "celebrating", "sleepy",
];
export const ZAZOO_ACTIONS: ZazooAction[] = ["idle", "meditating", "sneaking", "hiding"];
