import { Component, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import type { Persona } from '../../shared/api'

const rooms = ['library', 'classroom', 'home', 'office'] as const
const colors = ['#438665', '#5580aa', '#c2a15c', '#a47590', '#a36d54']
const centers: [number, number, number][] = [[-4, 0, -3], [4, 0, -3], [-4, 0, 3], [4, 0, 3]]

function Room({ position, color }: { position: [number, number, number]; color: string }) {
  return <group position={position}>
    <mesh position={[0, -.08, 0]} receiveShadow>
      <boxGeometry args={[6.4, .16, 4.8]} /><meshStandardMaterial color={color} />
    </mesh>
    <mesh position={[0, .9, -2.3]}>
      <boxGeometry args={[6.4, 1.8, .15]} /><meshStandardMaterial color="#d1d8cf" />
    </mesh>
    {[-1.8, 0, 1.8].map(x => <group key={x} position={[x, 0, -.6]}>
      <mesh position={[0, .65, 0]}><boxGeometry args={[1.1, .1, .7]} /><meshStandardMaterial color="#786550" /></mesh>
      <mesh position={[0, .32, 0]}><boxGeometry args={[.12, .64, .12]} /><meshStandardMaterial color="#665444" /></mesh>
      <mesh position={[0, .83, -.12]} rotation={[-.14, 0, 0]}>
        <boxGeometry args={[.45, .3, .035]} /><meshStandardMaterial color="#25382e" />
      </mesh>
    </group>)}
  </group>
}

function Character({ persona, index, selected, onSelect }: {
  persona: Persona; index: number; selected: boolean; onSelect: (id: string) => void
}) {
  const roomIndex = rooms.indexOf(persona.scenario.location_id)
  const center = centers[roomIndex]
  const slot = Math.floor(index / 4)
  const x = center[0] - 1.8 + slot * 1.8
  return <group position={[x, 0, center[2] + .5]} onClick={event => {
    event.stopPropagation(); onSelect(persona.id)
  }}>
    <mesh position={[0, 1.35, 0]}><boxGeometry args={[.45, .45, .45]} /><meshStandardMaterial color="#d0ac8a" /></mesh>
    <mesh position={[0, .88, 0]}><boxGeometry args={[.52, .5, .32]} /><meshStandardMaterial color={colors[index % 5]} /></mesh>
    {[-.15, .15].map(xPos => <mesh key={xPos} position={[xPos, .34, 0]}>
      <boxGeometry args={[.16, .6, .23]} /><meshStandardMaterial color="#35423b" />
    </mesh>)}
    {selected && <mesh position={[0, .025, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[.48, .61, 32]} /><meshBasicMaterial color="#1a6b4b" />
    </mesh>}
  </group>
}

class WorldBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    return this.state.failed ? <p role="status">3D rendering unavailable. Select any persona below.</p> : this.props.children
  }
}

export default function PersonaWorld({ personas, selected, onSelect }: {
  personas: Persona[]; selected: string; onSelect: (id: string) => void
}) {
  return <WorldBoundary><div className="persona-world" aria-label="Illustrative campus with ten selectable synthetic characters">
    <Canvas camera={{ position: [12, 15, 18], fov: 42 }} dpr={[1, 1.5]}
      fallback={<p>WebGL unavailable. Use the persona selection buttons below.</p>}>
      <color attach="background" args={['#e8eeea']} />
      <ambientLight intensity={1.2} /><directionalLight position={[8, 14, 8]} intensity={1.8} />
      <mesh position={[0, -.2, 0]}><boxGeometry args={[18, .2, 14]} /><meshStandardMaterial color="#b6c6b7" /></mesh>
      {centers.map((center, index) => <Room key={rooms[index]} position={center} color={['#e2d9bd', '#cbd9df', '#dccdcc', '#cfd9c5'][index]} />)}
      {personas.slice(0, 10).map((persona, index) => <Character key={persona.id} persona={persona}
        index={index} selected={persona.id === selected} onSelect={onSelect} />)}
      <OrbitControls makeDefault minPolarAngle={.2} maxPolarAngle={Math.PI / 2.3} minDistance={10} maxDistance={36} />
    </Canvas>
  </div></WorldBoundary>
}
