// Imports: side-effect, default, named with alias, namespace, relative path.

import "./side_effect.js";
import defaultExport from "some-pkg";
import { alpha as renamed, beta } from "./relative/mod.js";
import * as Star from "star-module";

export { beta } from "./reexport.js";
