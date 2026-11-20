// The coding agents Talpy Den can watch, and what each can do. Claude Code is
// the only one so far; a chat or account that names no agent is Claude Code's,
// so the Python backend's answers need no change.

export type AgentId = "claude-code";

// What an agent offers, so the UI can hide what it can't do.
export interface Capabilities {
  accounts: boolean; // several logins side by side
  planUsage: boolean; // the plan's 5-hour and weekly limits
  backgroundJobs: boolean; // chats that run without a window
  remoteControl: boolean; // answering a chat from elsewhere
  subagents: boolean; // helper agents inside a chat
  plans: boolean; // plan mode and its approval
  permissionAnswers: boolean; // answering permission asks and questions
  sshHosts: boolean; // chats on other machines
}

export interface AgentInfo {
  id: AgentId;
  name: string;
  capabilities: Capabilities;
}

export const CLAUDE_CODE: AgentInfo = {
  id: "claude-code",
  name: "Claude",
  capabilities: {
    accounts: true,
    planUsage: true,
    backgroundJobs: true,
    remoteControl: true,
    subagents: true,
    plans: true,
    permissionAnswers: true,
    sshHosts: true,
  },
};
