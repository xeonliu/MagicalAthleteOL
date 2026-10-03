import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { CuboidCollider, Physics, RigidBody, type RapierRigidBody } from "@react-three/rapier";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CanvasTexture, DoubleSide, ExtrudeGeometry, PCFSoftShadowMap, RepeatWrapping, Shape, SRGBColorSpace, TextureLoader, Vector3 } from "three";
import { FinishFireworks } from "./FinishFireworks";
import type { ActionMoment } from "../../eventPresentation";
import type { PlayerState, PropThrow } from "../../protocol";
import { TauntEffects } from "./TauntEffects";
import { useTranslation } from "react-i18next";

import { athleteText } from "../../i18n/athletes";
import { assetUrl } from "../../runtimeConfig";
import { actionId } from "../../gameClient";
import {
  assignRacerPlacements,
  BOARD_SIZE,
  RACER_PIECE_DIMENSIONS,
  racerPieceScale,
} from "./trackLayout";
import { createBoardCanvas, drawBoardArtwork, loadBoardAtlas } from "./boardArtwork";
import { TableDice, type DiceLauncher, type DiceThrowState } from "./TableDice";
import { boardTextureScale, racePixelRatio } from "./renderQuality";
import { festivalArtEnabled } from "../../artPack";

export interface RaceTableSceneProps {
  taunts?: PropThrow[];
  onPropImpact?: (event: PropThrow) => void;
  turnKey?: string;
  moment?: ActionMoment | null;
  players: PlayerState[];
  finishLine: number;
  trackName: "Standard" | "WildWilds";
  focus?: { athleteId: string; playerId?: string; close: boolean } | null;
  activePlayerId?: string | null;
  dice: {
    enabled: boolean;
    playbackBusy?: boolean;
    targetValue: number | null;
    restingValue: number;
    rollKey: string;
    autoThrow: boolean;
    resetKey: number;
    activePlayerName: string;
    onThrow: (throwId: string) => void;
    onSettled: () => void;
  };
}

const PLAYER_COLORS = ["#e8422e", "#4386c6", "#efbd25", "#43a45c", "#d45f9d", "#855ab0"];
const INK = "#1d1e21";

function FollowCameraRig({ players, finishLine, focus, activePlayerId, overview, reducedMotion }: Pick<RaceTableSceneProps, "players" | "finishLine" | "focus" | "activePlayerId"> & {
  overview: boolean; reducedMotion: boolean;
}) {
  const { camera, size } = useThree();
  const target = useRef(new Vector3());
  const desired = useMemo(() => new Vector3(), []);
  const initialized = useRef(false);
  const placements = assignRacerPlacements(players.flatMap((player, playerIndex) =>
    player.activeRacers.map((racer) => ({ ...racer, athleteId: racer.id, playerIndex }))), finishLine);
  const subject = placements.find((racer) => racer.athleteId === focus?.athleteId &&
    (!focus.playerId || players[racer.playerIndex].id === focus.playerId))
    ?? placements.find((racer) => players[racer.playerIndex].id === activePlayerId && !racer.finished && !racer.eliminated)
    ?? placements.find((racer) => !racer.finished && !racer.eliminated);
  useFrame((_, delta) => {
    const aspect = size.width / Math.max(size.height, 1);
    const portrait = aspect < 1;
    const close = !!focus?.close;
    const distance = overview ? Math.max(21, 14 / (Math.tan(Math.PI / 12) * aspect))
      : close ? (portrait ? 19 : 16) : portrait ? 23 : 30;
    const x = overview ? 0 : subject?.world.x ?? 0;
    const z = overview ? 0 : subject?.world.z ?? 0;
    const blend = reducedMotion || !initialized.current ? 1 : 1 - Math.exp(-delta * 3.2);
    target.current.lerp(desired.set(x, .25, z), blend);
    const elevation = Math.PI * (overview ? 72 : 57) / 180;
    desired.set(target.current.x, Math.sin(elevation) * distance, target.current.z + Math.cos(elevation) * distance);
    camera.position.lerp(desired, blend);
    camera.lookAt(target.current);
    camera.updateMatrixWorld();
    initialized.current = true;
  }, -2);
  return null;
}

function BoardArtwork({ trackName }: Pick<RaceTableSceneProps, "trackName">) {
  const { gl } = useThree();
  const texture = useMemo(() => {
    const next = new CanvasTexture(createBoardCanvas(trackName, festivalArtEnabled ? boardTextureScale(gl.capabilities.maxTextureSize) : 2));
    next.colorSpace = SRGBColorSpace;
    next.anisotropy = Math.min(festivalArtEnabled ? 16 : 8, gl.capabilities.getMaxAnisotropy());
    return next;
  }, [gl, trackName]);
  useEffect(() => {
    let active = true;
    loadBoardAtlas().then((image) => {
      if (!active) return;
      const context = (texture.image as HTMLCanvasElement).getContext("2d");
      if (context) {
        drawBoardArtwork(context, trackName, image);
        texture.needsUpdate = true;
      }
    }).catch(() => { /* The drawn course remains usable if the print cannot load. */ });
    return () => { active = false; texture.dispose(); };
  }, [texture, trackName]);
  return <mesh receiveShadow position={[0, 0.258, 0]} rotation={[-Math.PI / 2, 0, 0]} renderOrder={1}>
    <planeGeometry args={[BOARD_SIZE.width, BOARD_SIZE.depth]} />
    {festivalArtEnabled
      ? <meshPhysicalMaterial map={texture} transparent roughness={.78} metalness={0}
        clearcoat={.12} clearcoatRoughness={.85} polygonOffset polygonOffsetFactor={-1} />
      : <meshStandardMaterial map={texture} transparent roughness={.95} metalness={0}
        polygonOffset polygonOffsetFactor={-1} />}
  </mesh>;
}

function BoardBase() {
  const { gl } = useThree();
  const edgeTexture = useMemo(() => {
    if (!festivalArtEnabled) return null;
    const canvas = document.createElement("canvas");
    canvas.width = 128; canvas.height = 64;
    const context = canvas.getContext("2d");
    if (context) {
      context.fillStyle = "#b7a487"; context.fillRect(0, 0, 128, 64);
      // Subtle, deterministic paper fibres along the cut edge of the board.
      for (let i = 0; i < 170; i += 1) {
        const x = (i * 37) % 128; const y = (i * 19) % 64;
        context.strokeStyle = i % 2 ? "#efdfc33a" : "#63534124";
        context.lineWidth = i % 3 ? .5 : 1;
        context.beginPath(); context.moveTo(x, y); context.lineTo(x + 4 + i % 13, y + .3); context.stroke();
      }
      for (let y = 7; y < 64; y += 13) {
        context.fillStyle = "#66584428"; context.fillRect(0, y, 128, .7);
      }
    }
    const texture = new CanvasTexture(canvas);
    texture.colorSpace = SRGBColorSpace;
    texture.wrapS = RepeatWrapping; texture.wrapT = RepeatWrapping;
    texture.repeat.set(.5, 2);
    texture.anisotropy = Math.min(16, gl.capabilities.getMaxAnisotropy());
    return texture;
  }, [gl]);
  useEffect(() => () => edgeTexture?.dispose(), [edgeTexture]);
  const geometry = useMemo(() => {
    const x = BOARD_SIZE.width / 2;
    const z = BOARD_SIZE.depth / 2;
    const radius = .94;
    const shape = new Shape();
    shape.moveTo(-x + radius, -z);
    shape.lineTo(x - radius, -z);
    shape.quadraticCurveTo(x, -z, x, -z + radius);
    shape.lineTo(x, z - radius);
    shape.quadraticCurveTo(x, z, x - radius, z);
    shape.lineTo(-x + radius, z);
    shape.quadraticCurveTo(-x, z, -x, z - radius);
    shape.lineTo(-x, -z + radius);
    shape.quadraticCurveTo(-x, -z, -x + radius, -z);
    return new ExtrudeGeometry(shape, { depth: .3, bevelEnabled: true,
      bevelSize: festivalArtEnabled ? .07 : .015, bevelThickness: festivalArtEnabled ? .035 : .015,
      bevelSegments: festivalArtEnabled ? 8 : 2, steps: 1, curveSegments: festivalArtEnabled ? 40 : 16 });
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <mesh geometry={geometry} castShadow receiveShadow position={[0, festivalArtEnabled ? -.085 : -.065, 0]} rotation={[-Math.PI / 2, 0, 0]}>
    {festivalArtEnabled ? <>
      <meshPhysicalMaterial attach="material-0" color="#292a2e" roughness={.68} clearcoat={.15} clearcoatRoughness={.8} />
      <meshStandardMaterial attach="material-1" map={edgeTexture} color="#d5c4a7" roughness={.92} />
    </> : <meshStandardMaterial color={INK} roughness={0.9} />}
  </mesh>;
}

function TrackBoard({ trackName }: Pick<RaceTableSceneProps, "trackName">) {
  return <RigidBody type="fixed" colliders={false} friction={0.9} restitution={0.25}>
    <BoardBase />
    <CuboidCollider args={[BOARD_SIZE.width / 2, 0.17, BOARD_SIZE.depth / 2]} position={[0, 0.08, 0]} />
    <BoardArtwork trackName={trackName} />
  </RigidBody>;
}

function RacerPiece({ athleteId, name, color, world, slotCount, tripped, finished, finishPosition, eliminated, reducedMotion, highlight }: {
  highlight?: string;
  athleteId: string; name: string; color: string; world: { x: number; z: number };
  reducedMotion: boolean; slotCount: number; tripped: boolean; finished: boolean; finishPosition?: number | null; eliminated: boolean;
}) {
  const { gl } = useThree();
  const texture = useMemo(() => {
    const next = new TextureLoader().load(assetUrl(`assets/racer-tokens/${athleteId}.webp`));
    next.colorSpace = SRGBColorSpace;
    if (festivalArtEnabled) next.anisotropy = Math.min(16, gl.capabilities.getMaxAnisotropy());
    return next;
  }, [athleteId, gl]);
  useEffect(() => () => texture.dispose(), [texture]);
  const body = useRef<RapierRigidBody>(null);
  const initialPosition = useRef<[number, number, number]>([world.x, .285, world.z]);
  useFrame((_, delta) => {
    if (!body.current) return;
    const current = body.current.translation();
    const blend = reducedMotion ? 1 : 1 - Math.exp(-delta * 14);
    body.current.setNextKinematicTranslation({ x: current.x + (world.x - current.x) * blend,
      y: .285, z: current.z + (world.z - current.z) * blend });
  });
  const scale = racerPieceScale(slotCount);
  const baseHeight = 0.18 * scale;
  const baseRadius = RACER_PIECE_DIMENSIONS.baseRadius * scale;
  const portraitWidth = RACER_PIECE_DIMENSIONS.portraitWidth * scale;
  const portraitHeight = RACER_PIECE_DIMENSIONS.portraitHeight * scale;
  const lean = tripped ? -Math.PI / 2 : 0;
  return <RigidBody type="kinematicPosition" ref={body} colliders={false} position={initialPosition.current}>
    <CuboidCollider args={[portraitWidth / 2, (baseHeight + portraitHeight) / 2, 0.06 * scale]}
      position={[0, (baseHeight + portraitHeight) / 2, 0]} friction={0.7} restitution={0.45} />
    {highlight && <mesh position={[0, .025, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[baseRadius * 1.2, baseRadius * 1.6, 48]} />
      <meshBasicMaterial color={highlight} side={DoubleSide} depthTest={false} />
    </mesh>}
    <group rotation={[lean, 0, 0]} position={[0, tripped ? baseHeight / 2 : 0, 0]}>
      <mesh castShadow receiveShadow position={[0, baseHeight / 2, 0]}>
        <cylinderGeometry args={[baseRadius * 0.88, baseRadius, baseHeight, 24]} />
        <meshStandardMaterial color={eliminated ? "#777777" : color} roughness={0.62} />
      </mesh>
      <mesh castShadow position={[0, baseHeight + portraitHeight / 2 - 0.035 * scale, 0]}>
        <planeGeometry args={[portraitWidth, portraitHeight]} />
        <meshStandardMaterial map={texture} transparent alphaTest={0.08} side={DoubleSide} roughness={0.7} opacity={eliminated ? 0.55 : 1} />
      </mesh>
      {finished && <mesh position={[0, baseHeight + 0.01, baseRadius * 1.1]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[baseRadius * 0.52, baseRadius * 0.72, 24]} /><meshBasicMaterial color="#efbd25" />
      </mesh>}
    </group>
    {finished && (finishPosition === 1 || finishPosition === 2) && <FinishFireworks place={finishPosition} reducedMotion={reducedMotion} />}
    <mesh visible={false} name={name} />
  </RigidBody>;
}

function RacerFleet({ players, finishLine, reducedMotion, moment, focus }: Pick<RaceTableSceneProps, "players" | "finishLine" | "moment" | "focus"> & { reducedMotion: boolean }) {
  const racers = players.flatMap((player, playerIndex) => player.activeRacers.map((racer) => ({
    athleteId: racer.id,
    playerIndex,
    position: racer.position,
    finished: racer.finished,
    finishPosition: racer.finishPosition,
    eliminated: racer.eliminated,
  })));
  const { t } = useTranslation();
  const placements = assignRacerPlacements(racers, finishLine);
  return <>{placements.map((placement) => {
    const player = players[placement.playerIndex];
    const racer = player.activeRacers.find((item) => item.id === placement.athleteId)!;
    return <RacerPiece key={`${player.id}:${racer.id}`} athleteId={racer.id} name={athleteText(t, racer).name}
      highlight={moment?.target.playerId === player.id && moment.target.athleteId === racer.id ? "#ff9247"
        : moment?.source.playerId === player.id && moment.source.athleteId === racer.id ? "#37d7ec"
        : focus?.athleteId === racer.id && (!focus.playerId || focus.playerId === player.id) ? "#37d7ec" : undefined}
      reducedMotion={reducedMotion} color={PLAYER_COLORS[placement.playerIndex]} world={placement.world} slotCount={placement.slotCount} tripped={racer.tripped}
      finished={racer.finished} finishPosition={racer.finishPosition} eliminated={racer.eliminated} />;
  })}</>;
}

function TableAndBounds() {
  const { gl } = useThree();
  const texture = useMemo(() => {
    if (!festivalArtEnabled) return undefined;
    const next = new TextureLoader().load(assetUrl("assets/art-pack/festival-background.webp"));
    next.colorSpace = SRGBColorSpace;
    next.anisotropy = Math.min(16, gl.capabilities.getMaxAnisotropy());
    return next;
  }, [gl]);
  useEffect(() => () => texture?.dispose(), [texture]);
  return <RigidBody type="fixed" colliders={false}>
    <mesh receiveShadow position={[0, -0.12, 0]}>
      <boxGeometry args={[25.2, 0.2, 8.1]} />
      <meshStandardMaterial map={texture} color={festivalArtEnabled ? "#f1ead7" : "#b5ac99"} roughness={1} />
    </mesh>
    <CuboidCollider args={[12.6, 0.1, 4.05]} position={[0, -0.12, 0]} />
    <CuboidCollider args={[12.6, 0.8, 0.1]} position={[0, 0.4, -4.05]} />
    <CuboidCollider args={[12.6, 0.8, 0.1]} position={[0, 0.4, 4.05]} />
    <CuboidCollider args={[0.1, 0.8, 4.05]} position={[-12.6, 0.4, 0]} />
    <CuboidCollider args={[0.1, 0.8, 4.05]} position={[12.6, 0.4, 0]} />
  </RigidBody>;
}

function Scene({ turnKey, moment, taunts = [], onPropImpact, players, finishLine, trackName, dice, focus, activePlayerId, overview, reducedMotion, onDiceStateChange, registerDiceLauncher }: RaceTableSceneProps & {
  overview: boolean; reducedMotion: boolean;
  onDiceStateChange: (state: DiceThrowState) => void;
  registerDiceLauncher: (launcher: DiceLauncher | null) => void;
}) {
  return <>
    <FollowCameraRig players={players} finishLine={finishLine} focus={focus} activePlayerId={activePlayerId} overview={overview} reducedMotion={reducedMotion} />
    {!festivalArtEnabled && <color attach="background" args={["#b5ac99"]} />}
    <hemisphereLight intensity={1.25} color="#fff9e9" groundColor="#4b4945" />
    <directionalLight castShadow position={[-7, 14, 8]} intensity={1.75} shadow-mapSize={[2048, 2048]}
      shadow-bias={-0.00015} shadow-normalBias={0.025} shadow-radius={4}
      shadow-camera-near={4} shadow-camera-far={32}
      shadow-camera-left={-13} shadow-camera-right={13} shadow-camera-top={6} shadow-camera-bottom={-6} />
    <directionalLight position={[9, 7, -7]} intensity={0.38} color="#dce8ff" />
    <TauntEffects events={taunts} players={players} finishLine={finishLine} reducedMotion={reducedMotion} onImpact={onPropImpact} />
    <Physics gravity={[0, -12, 0]}>
      <TableAndBounds />
      <TrackBoard trackName={trackName} />
      <Suspense fallback={null}><RacerFleet focus={focus} moment={moment} players={players} finishLine={finishLine} reducedMotion={reducedMotion} /></Suspense>
      <TableDice turnKey={turnKey} {...dice} reducedMotion={reducedMotion} onStateChange={onDiceStateChange} registerLauncher={registerDiceLauncher} />
    </Physics>
  </>;
}

function HtmlFallback({ players, finishLine, dice }: RaceTableSceneProps) {
  const { t } = useTranslation();
  return <section className="race-table-fallback" aria-label={t("race3d.position")}>
    <div className="fallback-racers">
      {players.flatMap((player) => player.activeRacers.map((racer) => <div key={`${player.id}:${racer.id}`}>
        <strong>{athleteText(t, racer).name}</strong>
        <span>{racer.eliminated ? t("race3d.eliminated") : racer.finished ? t("race3d.finished") : `${racer.position} / ${finishLine}`}{racer.tripped ? t("race3d.trippedSuffix") : ""}</span>
      </div>))}
    </div>
    <div className={dice.targetValue ? "fallback-die landed" : "fallback-die"}>{dice.targetValue ?? dice.restingValue}</div>
    <button className="dice-throw-button" disabled={!dice.enabled} onClick={() => dice.onThrow(actionId())}>{t("race3d.roll")}</button>
  </section>;
}

export function RaceTableScene(props: RaceTableSceneProps) {
  const { t } = useTranslation();
  const [overview, setOverview] = useState(false);
  useEffect(() => {
    if (props.turnKey) setOverview(false);
  }, [props.turnKey]);
  const [diceState, setDiceState] = useState<DiceThrowState>("ready");
  const diceLauncher = useRef<DiceLauncher | null>(null);
  const registerDiceLauncher = useCallback((launcher: DiceLauncher | null) => { diceLauncher.current = launcher; }, []);
  const [webglAvailable] = useState(() => {
    try {
      const canvas = document.createElement("canvas");
      return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch { return false; }
  });
  const [reducedMotion] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  if (!webglAvailable) return <HtmlFallback {...props} />;
  const status = diceState === "preparing" ? t("race3d.preparing")
    : diceState === "settled" && props.dice.targetValue ? t("race3d.rollingValue", { value: props.dice.targetValue })
      : diceState === "rolling" || diceState === "settling" ? t("race3d.playerRolling", { name: props.dice.activePlayerName })
        : props.dice.playbackBusy ? t("race3d.playingAction")
          : props.dice.enabled ? t("race3d.dragToThrow") : t("race3d.waitingFor", { name: props.dice.activePlayerName });
  return <section className={`race-table-3d ${props.dice.enabled ? "dice-enabled" : ""}`} aria-label={t("race3d.table")}>
    <div className="race-table-viewport">
    <Canvas shadows dpr={festivalArtEnabled ? racePixelRatio(window.devicePixelRatio || 1) : [1, 1.75]} camera={{ position: [0, 19, 9], fov: 30, near: 0.1, far: 300 }}
      gl={{ antialias: true, alpha: festivalArtEnabled, powerPreference: "high-performance" }}
      onCreated={({ gl }) => { gl.shadowMap.type = PCFSoftShadowMap; }}>
      <Scene {...props} overview={overview} reducedMotion={reducedMotion} onDiceStateChange={setDiceState} registerDiceLauncher={registerDiceLauncher} />
    </Canvas>
    </div>
    <div className="camera-controls" role="group" aria-label={t("race3d.camera")}>
      <button aria-pressed={!overview} onClick={() => setOverview(false)}>{t("race3d.follow")}</button>
      <button aria-pressed={overview} onClick={() => setOverview(true)}>{t("race3d.overview")}</button>
    </div>
    <div className="table-dice-hud" aria-live="polite">
      <strong>{status}</strong>
      <button className="dice-throw-button" disabled={!props.dice.enabled || diceState !== "ready"} onClick={() => {
        const throwId = actionId();
        if (diceLauncher.current?.(throwId)) props.dice.onThrow(throwId);
      }}>{t("race3d.roll")}</button>
    </div>
  </section>;
}
