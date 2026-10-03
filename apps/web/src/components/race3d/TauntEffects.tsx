import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { DoubleSide, Group, Mesh, Vector3 } from "three";
import type { PlayerState, PropThrow } from "../../protocol";
import { assignRacerPlacements } from "./trackLayout";
import { eggGeometry, tomatoGeometry, splatGeometry, PROP_FLIGHT_SECONDS, PROP_SPLASH_SECONDS } from "./propGeometry";

function TomatoLeaves() {
  return <group position={[0, .17, 0]}>
    <mesh position={[0, .045, 0]} rotation={[.2, 0, -.15]}><cylinderGeometry args={[.014, .022, .1, 8]} /><meshStandardMaterial color="#41642a" roughness={.8} /></mesh>
    {Array.from({length: 5}, (_, i) => <group key={i} rotation={[0, i * Math.PI * 2 / 5, 0]}>
      <mesh position={[.065, -.005, 0]} rotation={[0, 0, -.38]} scale={[.13, .014, .036]}>
        <sphereGeometry args={[1, 12, 8]} /><meshStandardMaterial color={i % 2 ? "#578438" : "#3c692c"} roughness={.65} />
      </mesh>
    </group>)}
  </group>;
}

function FlyingProp({ event, start, end, reducedMotion, flatTarget, onImpact }: {
  event: PropThrow; start: Vector3; end: Vector3; reducedMotion: boolean; flatTarget: boolean; onImpact?: (event: PropThrow) => void;
}) {
  const projectile = useRef<Group>(null), impact = useRef<Group>(null);
  const fragments = useRef<Group>(null), droplets = useRef<Group>(null), puddle = useRef<Group>(null);
  const elapsed = useRef(0);
  const impactReported = useRef(false);
  const origin = useRef(start.clone()), target = useRef(end.clone());
  const egg = event.item === "egg";
  const geometry = useMemo(() => egg ? eggGeometry() : tomatoGeometry(), [egg]);
  const splats = useMemo(() => [splatGeometry(.42, 2), splatGeometry(.26, 5), splatGeometry(.17, 9)], []);
  useEffect(() => () => { geometry.dispose(); splats.forEach(shape => shape.dispose()); }, [geometry, splats]);
  useFrame((_, delta) => {
    elapsed.current += delta;
    const duration = reducedMotion ? 0 : PROP_FLIGHT_SECONDS;
    const progress = duration ? Math.min(1, elapsed.current / duration) : 1;
    const age = elapsed.current - duration;
    if (projectile.current) {
      projectile.current.visible = progress < 1;
      projectile.current.position.lerpVectors(origin.current, target.current, progress);
      projectile.current.position.y += Math.sin(progress * Math.PI) * 1.7;
      projectile.current.rotation.set(progress * Math.PI * 3, progress * 2, progress * Math.PI * 2);
    }
    if (!impact.current) return;
    impact.current.visible = age >= 0 && age < PROP_SPLASH_SECONDS;
    impact.current.position.set(target.current.x, .283, target.current.z);
    if (age < 0 || age >= PROP_SPLASH_SECONDS) return;
    if (!impactReported.current) { impactReported.current = true; onImpact?.(event); }
    const fade = Math.min(1, (PROP_SPLASH_SECONDS - age) / .35);
    impact.current.traverse(node => {
      if (node instanceof Mesh) {
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        for (const material of materials) {
          material.userData.propOpacity ??= material.opacity;
          material.transparent = true; material.opacity = material.userData.propOpacity * fade;
        }
      }
    });
    if (puddle.current) {
      const spread = reducedMotion ? 1 : .35 + .65 * (1 - Math.exp(-age * 11));
      puddle.current.scale.set(spread, 1, spread);
    }
    const flyAge = reducedMotion ? .9 : age;
    droplets.current?.children.forEach((drop, i) => {
      const angle = i * 2.39996, speed = 1.3 + (i % 5) * .35;
      const height = .55 + (.25 + (i % 7) * .22) * flyAge - 4.5 * flyAge * flyAge;
      drop.position.set(Math.cos(angle) * speed * Math.min(flyAge, .6), Math.max(.025, height), Math.sin(angle) * speed * Math.min(flyAge, .6));
      const landed = height <= .025;
      drop.scale.set(landed ? 1.6 : .8, landed ? .25 : 1.4, 1);
    });
    fragments.current?.children.forEach((fragment, i) => {
      const angle = i * 2.39996 + .7, time = Math.min(flyAge, .65);
      fragment.position.set(Math.cos(angle) * time * (1 + i * .09), Math.max(.03, .55 + time * 1.6 - 5 * time * time), Math.sin(angle) * time * (1 + i * .09));
      fragment.rotation.set(time * (3 + i), angle + time * 3, time * (2 - i));
    });
  });
  return <>
    <group ref={projectile} name={`prop-flight-${event.item}`}>
      <mesh geometry={geometry} castShadow><meshPhysicalMaterial color={egg ? "#f6e8cb" : "#d72c18"} roughness={egg ? .42 : .25} clearcoat={egg ? .12 : .85} clearcoatRoughness={.18} /></mesh>
      {!egg && <TomatoLeaves />}
    </group>
    <group ref={impact} visible={false} name={`prop-impact-${event.item}`}>
      <group ref={puddle}>
        <mesh geometry={splats[0]} rotation={[-Math.PI / 2, 0, .4]} position={[0, .008, 0]}><meshPhysicalMaterial color={egg ? "#eee5bb" : "#d32a14"} opacity={egg ? .48 : .85} roughness={.18} clearcoat={1} clearcoatRoughness={.12} transparent depthWrite={false} /></mesh>
        <mesh geometry={splats[1]} rotation={[-Math.PI / 2, 0, -.4]} position={[.055, .011, -.02]}><meshPhysicalMaterial color={egg ? "#fff4d1" : "#f05024"} opacity={egg ? .55 : .8} roughness={.14} clearcoat={1} transparent depthWrite={false} /></mesh>
        {egg ? <mesh position={[.035, .035, -.025]} scale={[.17, .035, .145]}><sphereGeometry args={[1, 24, 16]} /><meshPhysicalMaterial color="#f6ae08" roughness={.2} clearcoat={1} /></mesh>
          : <group scale={[1, .18, 1]} position={[.05, -.02, 0]}><TomatoLeaves /></group>}
      </group>
      <group position={[0, target.current.y - .283, flatTarget ? 0 : .085]} rotation={[flatTarget ? -Math.PI / 2 : 0, 0, 0]}>
        <mesh geometry={splats[1]} scale={[.85, 1, 1]}><meshPhysicalMaterial color={egg ? "#fff0cb" : "#e63718"} opacity={egg ? .6 : .9} roughness={.2} clearcoat={1} side={DoubleSide} transparent depthWrite={false} /></mesh>
        <mesh geometry={splats[2]} position={[.02, -.015, .012]} scale={[.8, .72, 1]}><meshPhysicalMaterial color={egg ? "#f8b813" : "#fc5929"} roughness={.22} clearcoat={1} side={DoubleSide} transparent depthWrite={false} /></mesh>
        {[0, 1, 2].map(i => <mesh key={i} position={[(i - 1) * .09, -.17 - i * .025, 0]} scale={[.017 + i * .004, .1 + i * .025, .007]}><sphereGeometry args={[1, 12, 8]} /><meshPhysicalMaterial color={egg ? "#f8eccb" : "#d8391b"} roughness={.2} clearcoat={1} transparent /></mesh>)}
      </group>
      <group ref={droplets}>{Array.from({length: 22}, (_, i) => <mesh key={i}><sphereGeometry args={[.012 + (i % 4) * .005, 10, 8]} /><meshPhysicalMaterial color={egg ? i % 4 ? "#f6edca" : "#edb114" : i % 3 ? "#e63e20" : "#ff6736"} opacity={egg && i % 4 ? .65 : 1} roughness={.2} clearcoat={1} transparent /></mesh>)}</group>
      <group ref={fragments}>{Array.from({length: egg ? 8 : 6}, (_, i) => <mesh key={i} scale={egg ? [1, 1.2, 1] : [1, .7, 1]}><sphereGeometry args={[egg ? .14 : .1, 12, 8, i * .7, 1.1, .5, .9]} /><meshPhysicalMaterial color={egg ? i % 2 ? "#fff8e4" : "#e4d7b6" : "#c92412"} roughness={egg ? .65 : .3} clearcoat={egg ? 0 : .8} side={DoubleSide} transparent /></mesh>)}</group>
      {!egg && Array.from({length: 9}, (_, i) => <mesh key={i} position={[Math.cos(i * 2.4) * .32, .02, Math.sin(i * 2.4) * .32]} scale={[.018, .006, .03]}><sphereGeometry args={[1, 8, 6]} /><meshStandardMaterial color="#f8ce7b" roughness={.4} transparent /></mesh>)}
    </group>
  </>;
}

export function TauntEffects({ events, players, finishLine, reducedMotion, onImpact }: {
  events: PropThrow[]; players: PlayerState[]; finishLine: number; reducedMotion: boolean; onImpact?: (event: PropThrow) => void;
}) {
  const positions = useMemo(() => assignRacerPlacements(players.flatMap((p, playerIndex) => p.activeRacers.map(r => ({...r, athleteId:r.id, playerIndex}))), finishLine), [players, finishLine]);
  return <>{events.map(event => {
    const target = positions.find(p => players[p.playerIndex].id === event.targetPlayerId && !p.finished && !p.eliminated)
      ?? positions.find(p => players[p.playerIndex].id === event.targetPlayerId);
    if (!target) return null;
    const source = positions.find(p => players[p.playerIndex].id === event.actorId);
    const racer = players[target.playerIndex].activeRacers.find(r => r.id === target.athleteId);
    const flatTarget = !!racer?.tripped;
    const end = new Vector3(target.world.x, flatTarget ? .41 : .8, target.world.z - (flatTarget ? .45 : 0));
    const start = source ? new Vector3(source.world.x, .8, source.world.z) : end.clone().add(new Vector3(-2, 0, 2));
    return <FlyingProp key={event.id} event={event} start={start} end={end} reducedMotion={reducedMotion} flatTarget={flatTarget} onImpact={onImpact} />;
  })}</>;
}
