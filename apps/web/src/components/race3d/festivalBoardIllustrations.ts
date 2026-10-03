import i18n from "../../i18n";

const INK = "#202125";

function path(context: CanvasRenderingContext2D, outline: string, fill: string, width = 1.8) {
  const shape = new Path2D(outline);
  context.fillStyle = fill;
  context.strokeStyle = INK;
  context.lineWidth = width;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.fill(shape);
  context.stroke(shape);
}

function star(context: CanvasRenderingContext2D, outer: number, inner: number, color: string) {
  context.beginPath();
  for (let i = 0; i < 10; i += 1) {
    const angle = -Math.PI / 2 + i * Math.PI / 5;
    const radius = i % 2 ? inner : outer;
    const x = 50 + Math.cos(angle) * radius;
    const y = 51 + Math.sin(angle) * radius;
    if (i) context.lineTo(x, y); else context.moveTo(x, y);
  }
  context.closePath();
  context.fillStyle = color;
  context.strokeStyle = INK;
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.fill(); context.stroke();
}

function scoringStar(context: CanvasRenderingContext2D, alternate: boolean) {
  context.fillStyle = alternate ? "#477ead" : "#567db8";
  context.fillRect(0, 0, 100, 100);
  // The original two award spaces use nested stars and colored corner bands.
  path(context, "M0 1 H28 V8 H8 V19 H0 Z M72 1 H100 V19 H92 V8 H72 Z", alternate ? "#df7baf" : "#66a55c");
  path(context, "M0 20 H12 V12 H28 V18 H18 V26 H0 Z M72 12 H88 V20 H100 V26 H82 V18 H72 Z", alternate ? "#f1cc55" : "#df8eba", 1.2);
  star(context, 49, 24, alternate ? "#df6448" : "#f3d264");
  star(context, 39, 17, alternate ? "#62a160" : "#d08abb");
  context.font = '900 45px "Arial Black", sans-serif';
  context.textAlign = "center"; context.textBaseline = "middle";
  context.strokeStyle = INK; context.lineWidth = 2.2;
  context.fillStyle = alternate ? "#f5d565" : "#cb654e";
  context.strokeText("1", 50, 56); context.fillText("1", 50, 56);
}

function trip(context: CanvasRenderingContext2D, step: number) {
  context.fillStyle = step === 17 ? "#f1cc4c" : step === 26 ? "#bb85b8" : "#de654d";
  context.fillRect(0, 0, 100, 100);
  if (step === 26) {
    path(context, "M0 0 H68 L37 35 H0 Z", "#69a154", 1.2);
    path(context, "M100 -2 L66 9 Q45 16 43 32 L65 47 Q82 48 96 41 L104 31 Z", "#d88fbb");
    path(context, "M64 30 l12 -7 M68 34 l12 -7 M82 20 l4 -5", "transparent", 1.4);
    // Curved rope under the foot, with the green sole visible below it.
    path(context, "M-5 45 Q16 32 45 41 Q62 47 83 37 L88 45 Q65 56 42 49 Q18 42 0 55 Z", "#dc8655");
    for (let x = 3; x < 86; x += 6) {
      const y = 45 + Math.sin(x / 15) * 4;
      path(context, `M${x} ${y - 5} q5 3 2 10`, "transparent", 1.1);
    }
    path(context, "M7 51 Q29 42 40 52 L41 60 Q25 69 11 61 Z", "#70a964");
  } else {
    if (step === 17) {
      path(context, "M42 37 L49 24 L57 36 L69 25 L65 41 L88 34 L76 46 L98 47 L83 55 L93 65 L73 62 L74 73 L59 62 L46 74 L43 62 L25 65 L35 52 L19 45 Z", "#f9e589", 1.2);
    }
    path(context, "M-8 -4 H81 L56 31 L30 36 L7 15 Z", step === 17 ? "#e77445" : "#638ec2");
    for (let x = 11; x < 72; x += 9) path(context, `M${x} -2 L${x - 23} 24`, "transparent", 1.1);
    path(context, "M23 23 Q29 18 35 23 L46 32 L58 33 Q67 29 76 39 L88 44 Q93 49 86 54 L51 56 Q35 55 22 46 L12 36 Z", step === 17 ? "#292b2d" : "#e46c4c");
    path(context, "M20 42 Q42 56 58 50 L86 48 L87 56 Q64 64 44 57 Q26 53 17 46 Z", step === 17 ? "#f2d55e" : "#f9f1dd", 1.4);
    path(context, "M46 31 l8 7 M51 29 l8 7 M57 29 l8 7", "transparent", 1.2);
    if (step === 5) {
      path(context, "M66 29 Q72 22 77 28 Q85 24 87 32 Q97 30 97 40 Q99 48 90 48 L78 43 Z", "#f9f3de", 1.4);
      path(context, "M78 31 l3 3 M85 35 l3 3 M90 40 l3 1", "transparent", 1.1);
    }
  }
  context.save();
  context.translate(51, 82); context.rotate(-.035);
  const label = i18n.t("board.trip");
  context.font = '900 23px "Microsoft YaHei", "Noto Sans SC", sans-serif';
  context.textAlign = "center"; context.textBaseline = "middle";
  context.lineJoin = "round"; context.strokeStyle = INK; context.lineWidth = 3.3;
  context.fillStyle = step === 17 ? "#83b7e4" : step === 26 ? "#f7de67" : "#fff6e5";
  context.strokeText(label, 0, 0, 91); context.fillText(label, 0, 0, 91);
  context.restore();
}

/** Native paths keep the familiar marks sharp at every canvas texture scale. */
export function drawFestivalSpecialTile(context: CanvasRenderingContext2D, step: number, x: number, y: number, width: number, height: number): boolean {
  if (![1, 5, 13, 17, 26].includes(step)) return false;
  context.save();
  context.translate(x, y); context.scale(width / 100, height / 100);
  context.beginPath(); context.roundRect(0, 0, 100, 100, 5); context.clip();
  if (step === 1 || step === 13) scoringStar(context, step === 13); else trip(context, step);
  context.restore();
  return true;
}
