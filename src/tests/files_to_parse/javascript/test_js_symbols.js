// Symbols: functions, class, methods, fields, const/let/var, generator, nested function.

export const TOP = 1;
let counter = 0;
var legacy = 2;

export function outer() {
  function inner() {
    return counter;
  }
  return inner;
}

export function* gen() {
  yield 1;
}

export class Base {}

export class Widget extends Base {
  count = 0;

  arrowRun = () => {
    return this.count;
  };

  method() {
    return TOP;
  }
}

export function testWidgetRuns() {
  return true;
}
