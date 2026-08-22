export type Morphs = Record<string, number>
export type HeadPose = { x: number; y: number; z: number }

const TAU = Math.PI * 2
const pos = (v: number) => (v < 0 ? 0 : v)
const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const easeInOutCubic = (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2)
const easeOutCubic = (p: number) => 1 - Math.pow(1 - p, 3)

class Blinker {
  private next = 2 + Math.random() * 2
  private start = -1
  private readonly dur = 0.16
  sample(t: number): number {
    if (this.start < 0 && t >= this.next) this.start = t
    if (this.start >= 0) {
      const p = (t - this.start) / this.dur
      if (p >= 1) {
        this.start = -1
        this.next = t + 2 + Math.random() * 4.5
        return 0
      }
      return Math.sin(p * Math.PI)
    }
    return 0
  }
}

export function yawnEnvelope(t: number): number {
  if (t < 0.42) return easeOutCubic(t / 0.42)
  if (t < 0.62) return 1
  return 1 - easeInOutCubic((t - 0.62) / 0.38)
}

abstract class GazeEngine {
  protected blink = new Blinker()
  protected lastT = -1
  protected gazeSX = 0
  protected gazeSY = 0
  protected gazeTX = 0
  protected gazeTY = 0
  protected gazeX = 0
  protected gazeY = 0
  protected sacStart = 0
  protected sacDur = 0.7
  protected nextSac = 0.6 + Math.random() * 0.8

  protected eyeMorphs(scaleX: number, scaleY: number, prog: number, yawn: number, deep: number, breath: number) {
    const gx = this.gazeX * (1 - yawn * scaleX)
    const gy = this.gazeY * (1 - yawn * scaleY)
    return { gx, gy, prog, deep, breath }
  }
}

export class IdleEngine extends GazeEngine {
  private nextDeep = 3 + Math.random() * 4
  private deepStart = -1
  private readonly deepDur = 2.2
  private yawnStart = -1
  private yawnDur = 2.8
  private nextYawnCheck = 5 + Math.random() * 4

  update(t: number): Morphs {
    this.lastT = t
    if (t >= this.nextSac) {
      this.gazeSX = this.gazeX
      this.gazeSY = this.gazeY
      this.gazeTX = (Math.random() - 0.5) * 0.75
      this.gazeTY = (Math.random() - 0.5) * 0.42
      if (Math.random() < 0.2) this.gazeTY += (Math.random() > 0.5 ? 1 : -1) * 0.16
      this.sacStart = t
      this.sacDur = 0.55 + Math.random() * 0.45
      this.nextSac = t + this.sacDur + 0.5 + Math.random() * 1.6
    }
    const prog = clamp((t - this.sacStart) / this.sacDur, 0, 1)
    const eased = easeInOutCubic(prog)
    if (prog < 1) {
      this.gazeX = lerp(this.gazeSX, this.gazeTX, eased)
      this.gazeY = lerp(this.gazeSY, this.gazeTY, eased)
    } else {
      this.gazeX = this.gazeTX + 0.018 * Math.sin(TAU * 0.11 * t + 0.7)
      this.gazeY = this.gazeTY + 0.012 * Math.sin(TAU * 0.09 * t + 1.3)
    }
    if (this.deepStart < 0 && t >= this.nextDeep) this.deepStart = t
    let deep = 0
    if (this.deepStart >= 0) {
      const p = (t - this.deepStart) / this.deepDur
      if (p >= 1) {
        this.deepStart = -1
        this.nextDeep = t + 4 + Math.random() * 5
      } else deep = Math.sin(p * Math.PI)
    }

    if (this.yawnStart < 0 && t >= this.nextYawnCheck) {
      this.nextYawnCheck = t + 2.8 + Math.random() * 2.2
      if (Math.random() < 0.15) {
        this.yawnStart = t
        this.yawnDur = 2.5 + Math.random() * 0.7
      }
    }
    let yawn = 0
    if (this.yawnStart >= 0) {
      const p = (t - this.yawnStart) / this.yawnDur
      if (p >= 1) {
        this.yawnStart = -1
      } else {
        yawn = yawnEnvelope(p)
      }
    }

    const shallow = 0.015 + 0.02 * (0.5 + 0.5 * Math.sin(TAU * 0.18 * t + 1))
    const breath = shallow + deep * 0.09
    const b = this.blink.sample(t)
    const yawnEye = yawn >= 0.75 ? (yawn - 0.75) / 0.25 : 0
    const eyeClose = Math.max(b, yawnEye)
    const gx = this.gazeX * (1 - yawn * 0.6)
    const gy = this.gazeY * (1 - yawn * 0.5)
    const eyeOutL = gx < 0 ? -gx * 0.9 : 0
    const eyeInL = gx > 0 ? gx * 0.9 : 0
    const eyeOutR = gx > 0 ? gx * 0.9 : 0
    const eyeInR = gx < 0 ? -gx * 0.9 : 0
    const up = gy > 0 ? gy * 0.95 : 0
    const down = gy < 0 ? -gy * 0.95 : 0
    const brow = 0.07 + deep * 0.05 + 0.03 * clamp(prog, 0, 1) + yawn * 0.12
    const jawYawn = 0.82
    const jaw = lerp(breath, jawYawn, yawn)
    return {
      eyeBlink_L: eyeClose,
      eyeBlink_R: eyeClose,
      eyeLookOut_L: eyeClose > 0.5 ? 0 : eyeOutL,
      eyeLookIn_L: eyeClose > 0.5 ? 0 : eyeInL,
      eyeLookOut_R: eyeClose > 0.5 ? 0 : eyeOutR,
      eyeLookIn_R: eyeClose > 0.5 ? 0 : eyeInR,
      eyeLookUp_L: eyeClose > 0.5 ? 0 : up,
      eyeLookUp_R: eyeClose > 0.5 ? 0 : up,
      eyeLookDown_L: eyeClose > 0.5 ? 0 : down,
      eyeLookDown_R: eyeClose > 0.5 ? 0 : down,
      eyeSquint_L: eyeClose > 0.1 ? eyeClose * 0.2 : 0.04 + deep * 0.08,
      eyeSquint_R: eyeClose > 0.1 ? eyeClose * 0.2 : 0.04 + deep * 0.08,
      eyeWide_L: 0,
      eyeWide_R: 0,
      browInnerUp: brow,
      jawOpen: jaw,
      cheekPuff: deep * 0.28 + yawn * 0.06,
      noseSneer_L: deep * 0.12,
      noseSneer_R: deep * 0.12,
      mouthClose: deep * 0.1 * (1 - yawn),
      mouthStretch_L: yawn * 0.42,
      mouthStretch_R: yawn * 0.42,
      mouthFunnel: yawn * 0.22,
    }
  }

  headPose(): HeadPose {
    let yawn = 0
    if (this.yawnStart >= 0) {
      const p = (this.lastT - this.yawnStart) / this.yawnDur
      if (p >= 0 && p < 1) {
        yawn = yawnEnvelope(p)
      }
    }
    const yaw = this.gazeX * 0.2 * (1 - yawn * 0.5)
    const pitch = this.gazeY * 0.12 - yawn * 0.14
    let deep = 0
    if (this.deepStart >= 0) {
      const p = (this.lastT - this.deepStart) / this.deepDur
      if (p >= 0 && p < 1) deep = Math.sin(p * Math.PI)
    }
    const roll = this.gazeX * 0.09
    return { x: pitch + deep * 0.05, y: yaw, z: roll }
  }
}

export class ThinkingEngine extends GazeEngine {
  constructor() {
    super()
    this.gazeSX = 0.08
    this.gazeSY = 0.06
    this.gazeTX = 0.08
    this.gazeTY = 0.06
    this.gazeX = 0.08
    this.gazeY = 0.06
    this.sacDur = 0.55
    this.nextSac = 0.4
  }
  private browL = 0.24
  private browR = 0.24
  private browLTarget = 0.24
  private browRTarget = 0.24
  private inner = 0.27
  private innerTarget = 0.27
  private browReturnAt = -1
  private nextBrowCheck = 1.2 + Math.random()
  private widePulse = 1
  private wideDur = 1.0
  private wideStart = -1
  private nextWideCheck = 1.8 + Math.random()

  private startWide(t: number) {
    this.wideStart = t
    this.widePulse = 1
    this.wideDur = 1.0
  }

  update(t: number): Morphs {
    const dt = this.lastT < 0 ? 0.016 : Math.min(t - this.lastT, 0.05)
    this.lastT = t
    if (t >= this.nextSac) {
      this.gazeSX = this.gazeX
      this.gazeSY = this.gazeY
      this.gazeTX = (Math.random() - 0.5) * 0.95
      this.gazeTY = (Math.random() - 0.5) * 0.42
      this.sacStart = t
      this.sacDur = 0.38 + Math.random() * 0.42
      this.nextSac = t + this.sacDur + 0.7 + Math.random() * 1.3
    }
    const prog = clamp((t - this.sacStart) / this.sacDur, 0, 1)
    const eased = easeInOutCubic(prog)
    if (prog < 1) {
      this.gazeX = lerp(this.gazeSX, this.gazeTX, eased)
      this.gazeY = lerp(this.gazeSY, this.gazeTY, eased)
    } else {
      this.gazeX = this.gazeTX
      this.gazeY = this.gazeTY
    }
    if (t >= this.nextWideCheck) {
      this.nextWideCheck = t + 0.9 + Math.random() * 1.6
      if (Math.random() < 0.19) this.startWide(t)
    }
    // 1s timeline: 0-0.18 ease in → 0.18-0.58 hold → 0.58-1.0 ease out
    if (this.wideStart >= 0) {
      const p = (t - this.wideStart) / this.wideDur
      if (p >= 1) {
        this.wideStart = -1
        this.widePulse = 0
      } else if (p < 0.18) {
        this.widePulse = easeOutCubic(p / 0.18)
      } else if (p < 0.58) {
        this.widePulse = 1
      } else {
        this.widePulse = 1 - easeInOutCubic((p - 0.58) / 0.42)
      }
    }
    if (t >= this.nextBrowCheck) {
      this.nextBrowCheck = t + 1.4 + Math.random() * 2.2
      if (this.browReturnAt < 0 && Math.random() < 0.34) {
        const side: 1 | -1 = Math.random() > 0.5 ? 1 : -1
        if (side > 0) {
          this.browLTarget = 0.58 + Math.random() * 0.12
          this.browRTarget = 0.15 + Math.random() * 0.08
        } else {
          this.browLTarget = 0.15 + Math.random() * 0.08
          this.browRTarget = 0.58 + Math.random() * 0.12
        }
        this.innerTarget = 0.32 + Math.random() * 0.1
        this.browReturnAt = t + 0.55 + Math.random() * 0.65
      }
    }
    if (this.browReturnAt > 0 && t >= this.browReturnAt) {
      this.browLTarget = 0.22 + Math.random() * 0.05
      this.browRTarget = 0.22 + Math.random() * 0.05
      this.innerTarget = 0.26 + Math.random() * 0.06
      this.browReturnAt = -1
    }
    const k = Math.min(dt * 7.5, 1)
    this.browL += (this.browLTarget - this.browL) * k
    this.browR += (this.browRTarget - this.browR) * k
    this.inner += (this.innerTarget - this.inner) * k
    const b = this.blink.sample(t)
    const side = this.gazeX
    const eyeOutL = side < 0 ? -side : 0
    const eyeInL = side > 0 ? side : 0
    const eyeOutR = side > 0 ? side : 0
    const eyeInR = side < 0 ? -side : 0
    const up = this.gazeY > 0 ? this.gazeY : 0
    const down = this.gazeY < 0 ? -this.gazeY : 0
    const wideBase = 0.14
    const wide = wideBase + this.widePulse * 0.68
    const browBoost = this.widePulse * 0.38
    const innerBoost = this.widePulse * 0.32
    const cheekDrop = this.widePulse
    const effBrowL = clamp(this.browL + browBoost, 0, 1)
    const effBrowR = clamp(this.browR + browBoost, 0, 1)
    const effInner = clamp(this.inner + innerBoost, 0, 1)
    const effSquint = this.widePulse > 0.35 ? 0 : 0.07 + this.widePulse * -0.07
    const effCheekSquint = clamp(0.08 - cheekDrop * 0.08, 0, 1)
    const lip = 0.05 + 0.03 * pos(Math.sin(TAU * 0.1 * t + 0.7)) + this.widePulse * 0.05
    return {
      eyeBlink_L: b,
      eyeBlink_R: b,
      eyeWide_L: b > 0.3 ? 0 : wide,
      eyeWide_R: b > 0.3 ? 0 : wide,
      eyeSquint_L: b > 0.1 ? b * 0.2 : effSquint,
      eyeSquint_R: b > 0.1 ? b * 0.2 : effSquint,
      eyeLookUp_L: b > 0.4 ? 0 : up,
      eyeLookUp_R: b > 0.4 ? 0 : up,
      eyeLookDown_L: b > 0.4 ? 0 : down,
      eyeLookDown_R: b > 0.4 ? 0 : down,
      eyeLookOut_L: b > 0.4 ? 0 : eyeOutL,
      eyeLookIn_L: b > 0.4 ? 0 : eyeInL,
      eyeLookOut_R: b > 0.4 ? 0 : eyeOutR,
      eyeLookIn_R: b > 0.4 ? 0 : eyeInR,
      browOuterUp_L: effBrowL,
      browOuterUp_R: effBrowR,
      browInnerUp: effInner,
      browDown_L: 0,
      browDown_R: 0,
      cheekSquint_L: effCheekSquint,
      cheekSquint_R: effCheekSquint,
      cheekPuff: 0,
      jawOpen: lip,
      mouthClose: 0,
      mouthPress_L: 0,
      mouthPress_R: 0,
    }
  }

  headPose(): HeadPose {
    const yaw = this.gazeX * 0.58
    const pitch = this.gazeY * 0.45
    const roll = this.gazeX * 0.38 + (this.browL - this.browR) * 0.22
    return { x: pitch, y: yaw, z: roll }
  }
}
