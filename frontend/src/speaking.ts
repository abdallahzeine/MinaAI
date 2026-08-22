/**
 * Procedural lip-sync-style speaking animation for the facecap.glb avatar.
 *
 * There is a single general speaking profile (kept from the former "sad"
 * emotion: low-energy mumbled jaw) with a constant 0.5 smile baseline on both
 * sides of the mouth. The mouth therefore always holds a 0.5 smile while the
 * avatar speaks, and the Jaw + the non-smile Mouth targets animate on top of
 * it to look like talking.
 *
 * The avatar has no audio track to sync to, so this generates believable,
 * non-repeating motion by summing incommensurate sine oscillators under a slow
 * "phrase" envelope (sentences come in bursts, not a hum) and a faster
 * "syllable" rhythm (~3-6 Hz). Frequency ratios are irrational so the motion
 * never lands on an exact loop.
 *
 * Only Jaw and Mouth group targets are touched, so brows, eyes and cheeks keep
 * whatever the idle expression clip or the manual sliders set. FaceDemo blends
 * the returned values on top of the base pose every frame, weighted by an eased
 * `speakWeight`, so speech fades in/out smoothly instead of snapping.
 */

export type SpeakingMorphs = Record<string, number>

const TAU = Math.PI * 2

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v)
/** Fold negative values to zero (a jaw can't open "backwards"). */
const pos = (v: number) => (v < 0 ? 0 : v)

// General speaking profile: kept from the former "sad" emotion (low-energy,
// mumbled jaw) + a constant 0.5 smile on both sides, always while speaking.
const SPEAK_AMP = 0.55
const SPEAK_BASELINE: SpeakingMorphs = { mouthSmile_L: 0.5, mouthSmile_R: 0.5 }

export class SpeakingEngine {
  /**
   * @param elapsedSec monotonically increasing time in seconds.
   * @returns sparse ARKit morph-target values for the Jaw + Mouth groups.
   *
   * Always computes; FaceDemo gates the visual effect with an eased
   * `speakWeight` so speech fades in/out smoothly instead of snapping.
   */
  update(elapsedSec: number): SpeakingMorphs {
    const t = elapsedSec

    // --- phrase envelope: slow swells so speech comes in bursts, not a hum ---
    const phrase = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(TAU * 0.14 * t + 0.7))

    // --- syllable rhythm: ~2-3.5 Hz (slowed ~40%), incommensurate + jitter
    const s1 = pos(Math.sin(TAU * 2.8 * t + 1.1))
    const s2 = pos(Math.sin(TAU * 2.0 * t + 2.4))
    const s3 = pos(Math.sin(TAU * 3.4 * t + 0.3))
    const jit = 0.1 * Math.sin(TAU * 1.1 * t + 4.2)
    const syll = (s1 + 0.6 * s2 + 0.4 * s3) / 2.0

    // --- jaw: the main talking driver ---
    const jaw = clamp((0.16 + 0.6 * phrase) * syll + jit, 0, 0.72) * SPEAK_AMP

    // --- non-smile mouth shapes that accompany / contrast the jaw (viseme-ish) ---
    const funnel = clamp(0.5 * pos(Math.sin(TAU * 1.0 * t + 0.6)) * (1 - jaw), 0, 0.55)
    const lowerDown = clamp(0.18 + 0.28 * jaw, 0, 0.5)
    const shrugLower = 0.3 * pos(Math.sin(TAU * 1.2 * t + 3))
    const press = 0.25 * pos(Math.sin(TAU * 0.6 * t + 1))
    const rollLower = 0.2 * pos(Math.sin(TAU * 0.8 * t + 2))

    const out: SpeakingMorphs = {
      jawOpen: jaw,
      mouthFunnel: funnel,
      mouthLowerDown_L: lowerDown,
      mouthLowerDown_R: lowerDown,
      mouthShrugLower: shrugLower,
      mouthPress_L: press,
      mouthPress_R: press,
      mouthRollLower: rollLower,
    }

    // --- constant 0.5 smile on both sides, always while speaking ---
    for (const k in SPEAK_BASELINE) out[k] = SPEAK_BASELINE[k]

    return out
  }
}
