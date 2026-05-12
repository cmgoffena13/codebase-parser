// TypeScript: interface with extends, type alias, parameter and return type refs.

interface A {
  id: number;
}

interface I extends A {
  x: string;
}

type B = { tag: string };
type T = B;

function typedFn(a: string): T {
  const v: I = { id: 1, x: "hi" };
  return { tag: v.x };
}
