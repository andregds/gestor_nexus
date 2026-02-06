import { getInstances, removeInstance } from "./instanceManager.js";

export function startCleanup() {
  setInterval(() => {
    const now = Date.now();

    getInstances().forEach(inst => {
      if (now - inst.lastSeen > 60000) {
        console.log("🧹 Removendo instância órfã:", inst.name);
        removeInstance(inst.name);
      }
    });
  }, 30000);
}
