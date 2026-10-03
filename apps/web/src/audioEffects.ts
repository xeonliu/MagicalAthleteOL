/** Short, bounded Web Audio cues shared by live playback and offline checks. */
function voice(audio: BaseAudioContext, output: AudioNode, frequency: number, when: number, duration: number, volume: number, type: OscillatorType = "triangle", endFrequency?: number) {
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  const start = audio.currentTime + when;
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, start);
  if (endFrequency) oscillator.frequency.exponentialRampToValueAtTime(endFrequency, start + duration * .8);
  gain.gain.setValueAtTime(.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + .015);
  gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  oscillator.connect(gain).connect(output);
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
  oscillator.start(start); oscillator.stop(start + duration + .02);
}

export function scheduleVictoryCue(audio: BaseAudioContext, output: AudioNode, place: 1 | 2): void {
  // First place gets a jaunty trumpet-like response and a sparkling chord;
  // second gets a lighter rising phrase so podium places sound distinct.
  const notes = place === 1 ? [523.25, 659.25, 783.99, 783.99, 1046.5] : [392, 493.88, 587.33, 783.99];
  const starts = place === 1 ? [0, .11, .22, .38, .52] : [0, .13, .26, .4];
  notes.forEach((frequency, i) => {
    const duration = i === notes.length - 1 ? .45 : .15;
    voice(audio, output, frequency, starts[i], duration, .052, "triangle");
    voice(audio, output, frequency * 2, starts[i], duration * .75, .011, "sine");
  });
  if (place === 1) {
    [261.63, 329.63, 392].forEach(frequency => voice(audio, output, frequency, .52, .55, .014, "sine"));
    [1567.98, 2093, 2637].forEach((frequency, i) => voice(audio, output, frequency, .76 + i * .08, .18, .016, "sine"));
    voice(audio, output, 100, 0, .12, .04, "sine", 48);
    voice(audio, output, 120, .38, .12, .035, "sine", 50);
  }
}

export function scheduleTripCue(audio: BaseAudioContext, output: AudioNode): void {
  // A quick slide, soft landing, then two rubbery rebounds.
  voice(audio, output, 880, 0, .23, .045, "sine", 190);
  voice(audio, output, 135, .19, .15, .07, "triangle", 55);
  voice(audio, output, 170, .3, .22, .047, "sine", 420);
  voice(audio, output, 210, .51, .18, .025, "sine", 300);
}

function wetNoise(audio: BaseAudioContext, output: AudioNode, when: number, duration: number, volume: number, cutoff: number) {
  const buffer = audio.createBuffer(1, Math.ceil(audio.sampleRate * duration), audio.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let i = 0; i < samples.length; i++) samples[i] = (Math.random() * 2 - 1) * Math.exp(-i / audio.sampleRate * 15);
  const source = audio.createBufferSource(), filter = audio.createBiquadFilter(), gain = audio.createGain();
  const start = audio.currentTime + when;
  source.buffer = buffer;
  filter.type = "lowpass";
  filter.frequency.setValueAtTime(cutoff, start);
  filter.frequency.exponentialRampToValueAtTime(160, start + duration);
  gain.gain.setValueAtTime(volume, start);
  gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  source.connect(filter).connect(gain).connect(output);
  source.onended = () => { source.disconnect(); filter.disconnect(); gain.disconnect(); };
  source.start(start); source.stop(start + duration);
}

export function schedulePropImpactCue(audio: BaseAudioContext, output: AudioNode, item: "egg" | "tomato"): void {
  if (item === "egg") {
    // Thin shell crack followed by the wet yolk/white landing.
    wetNoise(audio, output, 0, .055, .16, 6000);
    wetNoise(audio, output, .025, .24, .2, 1100);
    voice(audio, output, 155, .025, .13, .065, "sine", 55);
    wetNoise(audio, output, .075, .035, .065, 4200);
  } else {
    // A softer, lower squash with two little drops of juice.
    wetNoise(audio, output, 0, .32, .28, 900);
    voice(audio, output, 110, 0, .17, .075, "sine", 42);
    voice(audio, output, 310, .075, .09, .035, "sine", 105);
    wetNoise(audio, output, .13, .14, .1, 1600);
  }
}
