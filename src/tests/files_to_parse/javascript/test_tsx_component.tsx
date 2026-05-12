// TSX: component + handler call inside JSX attribute.

function handler() {
  return 0;
}

export function App() {
  return (
    <div className="app" onClick={() => handler()}>
      Hello
    </div>
  );
}
