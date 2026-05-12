# codebase-parser
Utilizes TreeSitter to parse a codebase and store the relationships. This empowers AI tooling to better understand and maneuver a codebase.

## MCP
Use the below config for Claude Desktop
```json
{
  "mcpServers": {
    "codebase-parser": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/codebase-parser-repo", "codebase-parser"]
    }
  }
}
```

Using it with the Claude Extension
1. Run `uv pip install -e .` in the codebase-parser repo
2. Run `claude mcp add --scope local codebase-parser -- codebase-parser`