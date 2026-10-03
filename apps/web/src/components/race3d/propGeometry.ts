import { CatmullRomCurve3, Shape, ShapeGeometry, SphereGeometry, Vector3 } from "three";

export const PROP_FLIGHT_SECONDS = .85;
export const PROP_SPLASH_SECONDS = 1.25;

export function eggGeometry() {
  const geometry = new SphereGeometry(1, 32, 24);
  const points = geometry.attributes.position;
  for (let i = 0; i < points.count; i++) {
    const y = points.getY(i), taper = 1 - .19 * y;
    points.setXYZ(i, points.getX(i) * .18 * taper, y * .25, points.getZ(i) * .18 * taper);
  }
  geometry.computeVertexNormals();
  return geometry;
}

export function tomatoGeometry() {
  const geometry = new SphereGeometry(1, 40, 28);
  const points = geometry.attributes.position;
  for (let i = 0; i < points.count; i++) {
    const x = points.getX(i), y = points.getY(i), z = points.getZ(i);
    const lobes = 1 + .065 * Math.cos(Math.atan2(z, x) * 5) * (1 - y * y);
    points.setXYZ(i, x * .23 * lobes, y * .2 - .03 * Math.pow(Math.max(0, y), 8), z * .23 * lobes);
  }
  geometry.computeVertexNormals();
  return geometry;
}

export function splatGeometry(radius: number, offset: number) {
  const outline = Array.from({length: 18}, (_, i) => {
    const angle = i * Math.PI * 2 / 18;
    const reach = radius * (1 + .16 * Math.sin(i * 2.3 + offset) + .07 * Math.cos(i * 4.1 + offset));
    return new Vector3(Math.cos(angle) * reach, Math.sin(angle) * reach, 0);
  });
  const shape = new Shape(), points = new CatmullRomCurve3(outline, true).getPoints(96);
  shape.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach(point => shape.lineTo(point.x, point.y));
  shape.closePath();
  return new ShapeGeometry(shape);
}
