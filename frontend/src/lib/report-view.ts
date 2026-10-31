/** Labels and groupings for the screening report view; scores and rules stay on the backend. */
import type { Correctness, EndReason, FlagKind, IntegrityFlag, NextStep, ReportDimensionName, ReportTopic, ResumeStatus, ScreeningReport, TopicStatus } from "./screenings.ts";

export const statusLabels: Record<TopicStatus, string> = {
  supported: "Supported",
  partly_supported: "Partly supported",
  not_shown: "Not shown",
  declined: "Unsure or declined",
  not_covered: "Not covered",
};
export const correctnessLabels: Record<Correctness, string> = {
  correct: "Correct",
  correct_after_hint: "Correct after a hint",
  comparable: "Comparable equivalent",
  partly_correct: "Partly correct",
  incorrect: "Incorrect",
  not_applicable: "",
};
export const resumeLabels: Record<ResumeStatus, string> = {
  met: "Shown",
  transferable: "Comparable",
  partial: "Partly shown",
  not_met: "Not shown",
  unknown: "Not in resume",
};
export const dimensionLabels: Record<ReportDimensionName, [string, string]> = {
  relevance: ["Relevance", "Answers address the questions asked"],
  specificity: ["Specificity", "Concrete tools, steps, numbers and outcomes"],
  ownership: ["Ownership", "What the candidate personally did"],
  explanation: ["Explanation", "How and why: approach, reasoning, results"],
};
export const categoryLabels: Record<ReportTopic["category"], string> = {
  mandatory: "Mandatory",
  experience: "Experience",
  preferred: "Preferred",
  qualification: "Qualification",
};
export const nextStepLabels: Record<NextStep, string> = {
  interview: "Recruiter or technical interview",
  gather_information: "Gather more information",
  human_review: "Human review",
};
export const endLabels: Record<EndReason, string> = {
  interviewer: "Closed by the interviewer",
  time_limit: "Reached the time limit",
  failure: "Stopped by a technical problem",
  ended_early: "Ended early",
};
export const flagLabels: Record<FlagKind, string> = {
  instruction_override: "Tried to override the AI's instructions",
  score_request: "Asked for a high score or recommendation",
  answer_request: "Asked the AI for the answer",
  prompt_probe: "Asked to see the AI's instructions",
};
export const detectedByLabels: Record<IntegrityFlag["detected_by"], string> = {
  rules: "Found by server rules",
  ai: "Found by the AI review",
  both: "Found by server rules and the AI review",
};

export interface FlagGroup { quote: string; labels: string[]; notes: string[]; detectedBy: string }

/** One entry per quoted sentence, since a single sentence can carry several attempts. */
export function flagGroups(flags: IntegrityFlag[]): FlagGroup[] {
  const groups = new Map<string, IntegrityFlag[]>();
  for (const flag of flags) groups.set(flag.quote, [...(groups.get(flag.quote) ?? []), flag]);
  return [...groups.entries()].map(([quote, items]) => {
    const sources = new Set(items.map((flag) => flag.detected_by));
    const detected = sources.has("both") || (sources.has("rules") && sources.has("ai")) ? "both" : [...sources][0];
    return {
      quote,
      labels: [...new Set(items.map((flag) => flagLabels[flag.kind]))],
      notes: [...new Set(items.filter((flag) => flag.detected_by !== "rules" && flag.note).map((flag) => flag.note))],
      detectedBy: detectedByLabels[detected],
    };
  });
}

/** The backend's interview threshold, shown as a marker on the score bar. */
export const INTERVIEW_THRESHOLD = 67;

export type Tone = "good" | "warn" | "muted" | "alert";
export const statusIcons: Record<TopicStatus, [string, Tone]> = {
  supported: ["✓", "good"],
  partly_supported: ["◐", "warn"],
  not_shown: ["✕", "warn"],
  declined: ["?", "muted"],
  not_covered: ["—", "muted"],
};

export const plain = (text: string) => text.replace(/\.$/, "");
export const topicIcon = (topic: ReportTopic): [string, Tone] => (topic.needs_check ? ["!", "warn"] : statusIcons[topic.status]);

export interface GlanceItem { topic: ReportTopic; detail: string }
export interface Glance { strengths: GlanceItem[]; verify: GlanceItem[]; uncovered: GlanceItem[] }

/** Strengths are clean supports; Verify is anything a recruiter should check; the rest was not covered. */
export function glance(report: ScreeningReport): Glance {
  const result: Glance = { strengths: [], verify: [], uncovered: [] };
  for (const topic of report.topics) {
    if (topic.status === "supported" && !topic.needs_check) {
      const how: Partial<Record<Correctness, string>> = { correct_after_hint: "Correct after a hint", comparable: "Comparable equivalent", correct: "Explained correctly" };
      result.strengths.push({ topic, detail: how[topic.correctness] ?? "Concrete example given" });
    } else if (topic.needs_check || topic.status === "partly_supported" || topic.status === "not_shown" || (topic.status === "declined" && topic.category === "mandatory")) {
      result.verify.push({ topic, detail: topic.note || statusLabels[topic.status] });
    } else {
      result.uncovered.push({ topic, detail: topic.status === "declined" ? "Candidate unsure" : "Not discussed" });
    }
  }
  return result;
}

const CATEGORY_ORDER: ReportTopic["category"][] = ["mandatory", "experience", "preferred", "qualification"];
export const topicsByCategory = (topics: ReportTopic[]) => [...topics].sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category));

/** Needs-check notes first, tied to their topic, then the model's follow-up questions. */
export function askNext(report: ScreeningReport): { question: string; topic: string }[] {
  const checks = report.topics.filter((topic) => topic.needs_check && topic.note).map((topic) => ({ question: `Clarify: ${topic.note}`, topic: plain(topic.description) }));
  return [...checks, ...report.follow_ups.map((question) => ({ question, topic: "" }))];
}

/** Plain-text notes for an ATS; built on demand and only ever placed on the clipboard. */
export function notesText(report: ScreeningReport): string {
  const groups = glance(report);
  const list = (items: GlanceItem[]) => (items.length ? items.map(({ topic, detail }) => `- ${plain(topic.description)} (${detail})`).join("\n") : "- None");
  const asks = askNext(report);
  const score = report.overall_score === null ? "n/a" : `${Math.round(report.overall_score)}/100`;
  const correctness = report.correctness_score === null ? "n/a" : `${Math.round(report.correctness_score)}%`;
  return [
    `Screening report: ${report.job_title} (${report.candidate_kind === "demo" ? "demo candidate" : "uploaded candidate"})`,
    `Suggested next step: ${nextStepLabels[report.next_step]} (AI-assisted; a recruiter decides)`,
    `Why: ${report.next_step_reasons.join("; ")}`,
    `Answer quality ${score} · Correctness ${correctness} · ${report.complete ? "Complete" : "Incomplete"}, ${report.candidate_answers} answers`,
    ...(report.integrity_flags.length
      ? ["", "Integrity flags (review the conversation):", ...flagGroups(report.integrity_flags).map((group) => `- ${group.labels.join("; ")}: "${group.quote}"`)]
      : []),
    "", "Strengths:", list(groups.strengths),
    "", "Verify:", list(groups.verify),
    "", "Not covered:", list(groups.uncovered),
    "", "Ask next:", asks.length ? asks.map(({ question }, index) => `${index + 1}. ${question}`).join("\n") : "- None",
    ...(report.summary ? ["", `AI summary: ${report.summary}`] : []),
    "", "Candidate statements are unverified claims from a temporary AI screening; nothing was stored.",
  ].join("\n");
}
