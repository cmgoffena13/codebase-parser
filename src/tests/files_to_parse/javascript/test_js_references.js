// References: calls, member access, optional chaining; filter console/Math.

function myFunc() {
  return 1;
}

const obj = { prop: 2, meth() { return 3; } };

function main() {
  myFunc();
  helper();
  obj.prop;
  obj.meth();
  maybe?.prop;
  maybe?.meth();
  const arr = [];
  arr[0];
  console.log("skip");
  Math.abs(-1);
}

function helper() {}
