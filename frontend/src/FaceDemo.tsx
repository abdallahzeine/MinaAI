import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'
import { SpeakingEngine } from './speaking'
import { IdleEngine, ThinkingEngine } from './motion'
import './FaceDemo.css'

export type AvatarPhase = 'idle' | 'listening' | 'thinking' | 'speaking'

export interface FaceDemoProps {
  phase: AvatarPhase
}

function useLatest<T>(value: T) {
  const ref = useRef(value)
  useEffect(() => {
    ref.current = value
  }, [value])
  return ref
}

export default function FaceDemo({ phase }: FaceDemoProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const phaseRef = useLatest(phase)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    let disposed = false

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth || 1, mount.clientHeight || 1, false)
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    const canvas = renderer.domElement
    canvas.className = 'face-canvas'
    mount.appendChild(canvas)

    const scene = new THREE.Scene()

    const camera = new THREE.PerspectiveCamera(
      45,
      (mount.clientWidth || 1) / (mount.clientHeight || 1),
      1,
      20,
    )
    camera.position.set(-0.215, 0.113, 3.522)

    const pmrem = new THREE.PMREMGenerator(renderer)
    const environment = new RoomEnvironment()
    const envRT = pmrem.fromScene(environment, 0.04)
    scene.environment = envRT.texture
    environment.traverse((o) => {
      const m = o as THREE.Mesh
      m.geometry?.dispose?.()
    })

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enabled = false

    let faceMesh: THREE.Mesh | null = null
    let headGroup: THREE.Group | null = null

    const clock = new THREE.Clock()
    const idle = new IdleEngine()
    const think = new ThinkingEngine()
    const speak = new SpeakingEngine()
    let elapsed = 0
    let idleWeight = 0
    let thinkWeight = 0
    let speakWeight = 0
    const ease = (current: number, target: number, delta: number) =>
      current + (target - current) * Math.min(delta * 8, 1)

    const headQuat = new THREE.Quaternion()
    const headEuler = new THREE.Euler()
    const headTarget = new THREE.Quaternion()
    const headEff = new THREE.Quaternion()

    const animate = () => {
      if (disposed) return
      const delta = clock.getDelta()
      elapsed += delta

      const p = phaseRef.current
      const idleTarget = p === 'idle' || p === 'listening' ? 1 : 0
      const thinkTarget = p === 'thinking' ? 1 : 0
      const speakTarget = p === 'speaking' ? 1 : 0
      idleWeight = ease(idleWeight, idleTarget, delta)
      thinkWeight = ease(thinkWeight, thinkTarget, delta)
      speakWeight = ease(speakWeight, speakTarget, delta)

      if (faceMesh) {
        const inf = faceMesh.morphTargetInfluences
        const dict = faceMesh.morphTargetDictionary
        if (inf && dict) {
          for (let i = 0; i < inf.length; i++) inf[i] = 0

          const overlay = (vals: Record<string, number>, w: number) => {
            if (w <= 0.001) return
            for (const name in vals) {
              const idx = dict[name]
              if (idx !== undefined) {
                inf[idx] = inf[idx] * (1 - w) + (vals[name] as number) * w
              }
            }
          }
          overlay(idle.update(elapsed), idleWeight)
          overlay(think.update(elapsed), thinkWeight)
          overlay(speak.update(elapsed), speakWeight)
        }
      }

      if (headGroup) {
        const isThinking = thinkWeight > 0.01
        const isIdle = idleWeight > 0.01 && !isThinking
        const pose = isThinking ? think.headPose() : idle.headPose()
        const hw = isThinking ? thinkWeight : isIdle ? idleWeight : 0

        headEuler.set(pose.x, pose.y, pose.z, 'XYZ')
        headTarget.setFromEuler(headEuler)
        headEff.identity().slerp(headTarget, hw)
        const k = Math.min(delta * 6, 1)
        headQuat.slerp(headEff, k)
        if (hw < 0.02) {
          headGroup.quaternion.identity()
          headQuat.identity()
        } else {
          headGroup.quaternion.copy(headQuat)
        }
      }

      renderer.render(scene, camera)
    }
    renderer.setAnimationLoop(animate)

    const ktx2 = new KTX2Loader().setTranscoderPath('/libs/basis/').detectSupport(renderer)
    const loader = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder)

    // Simple three.js example: load original facecap.glb as-is.
    // No eye pixel decoding, no brown tint. Animations (Idle/Thinking/Speaking
    // morphs + head slerp) are preserved.
    loader.load(
      '/models/gltf/facecap.glb',
      (gltf) => {
        if (disposed) return
        scene.add(gltf.scene)
        gltf.scene.traverse((o) => {
          const mesh = o as THREE.Mesh
          if (!faceMesh && mesh.isMesh && mesh.morphTargetDictionary) {
            faceMesh = mesh
            // Multiply color so eyebrows/details in map are kept (not solid replace)
            const origMat = mesh.material as THREE.MeshStandardMaterial
            const skinMat = origMat.clone()
            skinMat.color.set(0xcfa37e)
            skinMat.roughness = 0.75
            skinMat.metalness = 0
            // keep origMat.map (eyebrows etc.) — color multiplies with map
            mesh.material = skinMat
            headGroup = (mesh.parent as THREE.Group) ?? null
            if (headGroup && headGroup.type !== 'Group' && headGroup.type !== 'Scene') {
              headGroup = gltf.scene as unknown as THREE.Group
            }
          }
          // Old first style — eyes keep original material, no eye color change.
          // Animations preserved, eye pupil color left as original.
        })
        setStatus('ready')
      },
      undefined,
      (err: unknown) => {
        console.error('[FaceDemo] failed to load facecap.glb', err)
        if (!disposed) setStatus('error')
      },
    )

    const onResize = () => {
      const w = mount.clientWidth
      const h = mount.clientHeight
      if (w === 0 || h === 0) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h, false)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(mount)

    return () => {
      disposed = true
      ro.disconnect()
      renderer.setAnimationLoop(null)
      controls.dispose()
      scene.traverse((o) => {
        const m = o as THREE.Mesh
        m.geometry?.dispose?.()
        const mat = m.material
        const mats = Array.isArray(mat) ? mat : mat ? [mat as THREE.Material] : []
        for (const x of mats) {
          const anyMat = x as unknown as {
            map?: THREE.Texture
            normalMap?: THREE.Texture
            roughnessMap?: THREE.Texture
            metalnessMap?: THREE.Texture
            emissiveMap?: THREE.Texture
            dispose(): void
          }
          anyMat.map?.dispose?.()
          anyMat.normalMap?.dispose?.()
          anyMat.roughnessMap?.dispose?.()
          anyMat.emissiveMap?.dispose?.()
          x.dispose()
        }
      })
      envRT.dispose()
      pmrem.dispose()
      ktx2.dispose()
      renderer.dispose()
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas)
    }
  }, [])

  return (
    <div className="face-demo">
      <div className="face-mount" ref={mountRef} />
      {status !== 'ready' && (
        <div className={`face-overlay ${status}`}>
          {status === 'loading' ? 'loading…' : 'failed to load the avatar'}
        </div>
      )}
    </div>
  )
}
