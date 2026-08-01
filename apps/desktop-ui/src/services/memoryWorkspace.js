import { toSummaryView } from "../domain/viewModels.js";
import { coreApi } from "./coreApi.js";

export const memoryWorkspace = {
  async load() {
    const [index, summaries] = await Promise.all([
      coreApi.memoryIndexStatus(),
      coreApi.conversationSummaries(),
    ]);
    return { index, summaries: summaries.items.map(toSummaryView) };
  },
  async refreshSummaries() {
    const response = await coreApi.conversationSummaries();
    return response.items.map(toSummaryView);
  },
  async rebuildIndex() {
    await coreApi.rebuildMemoryIndex();
    return coreApi.memoryIndexStatus();
  },
  async generateSummary(sessionId) {
    await coreApi.generateConversationSummary(sessionId);
    return this.refreshSummaries();
  },
  async deleteSummary(id) {
    await coreApi.deleteConversationSummary(id);
    return this.refreshSummaries();
  },
};
