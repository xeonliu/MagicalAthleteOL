import { schedulePropImpactCue, scheduleTripCue, scheduleVictoryCue } from "./audioEffects";

let context: AudioContext | null = null;
let sfxOutput: GainNode | null = null;

export function getGameAudioContext() {
  if (typeof window === "undefined") return null;
  if (typeof AudioContext === "undefined") return null;
  try { context ??= new AudioContext(); } catch { return null; }
  if (context.state === "suspended") void context.resume().catch(() => {});
  return context;
}

function getSfxOutput(audio: AudioContext) {
  if (!sfxOutput) {
    sfxOutput = audio.createGain();
    sfxOutput.gain.value = 0.9;
    sfxOutput.connect(audio.destination);
  }
  return sfxOutput;
}

function tone(frequency: number, duration: number, start = 0, type: OscillatorType = "sine", volume = 0.045) {
  const audio = getGameAudioContext();
  if (!audio) return;
  const now = audio.currentTime + start;
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, now);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(volume, now + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
  oscillator.connect(gain).connect(getSfxOutput(audio));
  oscillator.start(now);
  oscillator.stop(now + duration + 0.02);
}

export function playDiceImpactSound() {
  tone(170, 0.065, 0, "triangle", 0.035);
}

export function playCharacterScoreSound() {
  tone(440, 0.12, 0, "triangle", 0.06);
  tone(554, 0.14, 0.09, "triangle", 0.07);
  tone(659, 0.2, 0.19, "triangle", 0.075);
}

export function playMoveSound() {
  tone(260, 0.06, 0, "triangle", 0.045);
  tone(330, 0.08, 0.06, "triangle", 0.055);
}

export function playPodiumSound(place: 1 | 2) {
  const audio = getGameAudioContext();
  if (audio) scheduleVictoryCue(audio, getSfxOutput(audio), place);
}

export function playTripSound() {
  const audio = getGameAudioContext();
  if (audio) scheduleTripCue(audio, getSfxOutput(audio));
}

export function playPropImpactSound(item: "egg" | "tomato") {
  const audio = getGameAudioContext();
  if (audio) schedulePropImpactCue(audio, getSfxOutput(audio), item);
}

export function unlockGameAudio() { getGameAudioContext(); }

export function playFireworkSound(place: 1 | 2) {
  const audio = getGameAudioContext();
  if (!audio || audio.state !== "running") return;
  playPodiumSound(place);
  for (let burst = 0; burst < 3; burst++) {
    const start = audio.currentTime + burst * .65;
    const whistle = audio.createOscillator();
    const envelope = audio.createGain();
    whistle.frequency.setValueAtTime(450, start);
    whistle.frequency.exponentialRampToValueAtTime(1500, start + .38);
    envelope.gain.setValueAtTime(.0001, start);
    envelope.gain.exponentialRampToValueAtTime(.012, start + .12);
    envelope.gain.exponentialRampToValueAtTime(.0001, start + .4);
    whistle.connect(envelope).connect(getSfxOutput(audio));
    whistle.start(start); whistle.stop(start + .41);
    const buffer = audio.createBuffer(1, Math.ceil(audio.sampleRate * .8), audio.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * Math.exp(-i / audio.sampleRate * 7);
    const noise = audio.createBufferSource();
    noise.buffer = buffer;
    const filter = audio.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(2200, start + .4);
    filter.frequency.exponentialRampToValueAtTime(350, start + 1.1);
    const gain = audio.createGain();
    gain.gain.value = .055;
    noise.connect(filter).connect(gain).connect(getSfxOutput(audio));
    noise.start(start + .4);
  }
}
