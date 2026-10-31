"use client";

import { useState } from "react";
import type { ScreeningReport } from "@/lib/screenings";
import {
  askNext, categoryLabels, correctnessLabels, dimensionLabels, endLabels, flagGroups, glance, INTERVIEW_THRESHOLD, nextStepLabels,
  notesText, plain, resumeLabels, statusLabels, topicIcon, topicsByCategory, type GlanceItem, type Tone,
} from "@/lib/report-view";

function Icon({ glyph, tone }: { glyph: string; tone: Tone }) {
  return <span className="mission-icon" data-tone={tone} aria-hidden="true">{glyph}</span>;
}

/** Supporting quotes stay collapsed so the report reads as a summary first. */
function Quotes({ quotes }: { quotes: string[] }) {
  if (!quotes.length) return null;
  const count = `${quotes.length} ${quotes.length === 1 ? "quote" : "quotes"}`;
  return (
    <details className="mission-report-evidence">
      <summary><span className="mission-report-closed">Show {count}</span><span className="mission-report-open">Hide {count}</span></summary>
      <ul className="mission-report-quotes">{quotes.map((quote) => <li key={quote}><blockquote>“{quote}”</blockquote></li>)}</ul>
    </details>
  );
}

function GlanceGroup({ kind, title, items, empty }: { kind: "strength" | "verify" | "uncovered"; title: string; items: GlanceItem[]; empty: string }) {
  return (
    <div className="mission-glance-group" data-kind={kind}>
      <h5>{title} ({items.length})</h5>
      {items.length ? (
        <ul>
          {items.map(({ topic, detail }) => {
            const [glyph, tone]: [string, Tone] = kind === "verify" ? ["!", "warn"] : topicIcon(topic);
            return <li key={topic.requirement_id}><Icon glyph={glyph} tone={tone} />{plain(topic.description)}<small>{detail}</small></li>;
          })}
        </ul>
      ) : <span className="mission-glance-empty">{empty}</span>}
    </div>
  );
}

/** Fallback for browsers or embedded views that block the asynchronous clipboard API. */
function copyWithSelection(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

/** The temporary screening report, recruiter-first: the suggestion and what to check, then the detail. */
export function ScreeningReportView({ report }: { report: ScreeningReport }) {
  const [copyStatus, setCopyStatus] = useState("");
  const groups = glance(report);
  const asks = askNext(report);
  const flags = flagGroups(report.integrity_flags);
  const score = report.overall_score === null ? null : Math.round(report.overall_score);

  async function copyNotes() {
    const text = notesText(report);
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch {
      copied = copyWithSelection(text);
    }
    setCopyStatus(copied ? "Copied. Paste it into your ATS notes." : "Copying is blocked in this browser.");
  }

  return (
    <article className="mission-report" aria-labelledby="screening-report-heading">
      <div className="mission-report-head">
        <div>
          <p className="mission-kicker">TEMPORARY · AI-ASSISTED · A RECRUITER DECIDES</p>
          <h3 id="screening-report-heading">Screening report</h3>
        </div>
        <div className="mission-report-actions">
          <span role="status" className="mission-help">{copyStatus}</span>
          <button type="button" className="mission-outline-button" onClick={() => void copyNotes()}>Copy as notes</button>
        </div>
      </div>

      <section className="mission-glance" aria-label="At a glance">
        <div className="mission-glance-top">
          <div>
            <p className="mission-glance-label">Suggested next step</p>
            <p className="mission-glance-step">{nextStepLabels[report.next_step]}</p>
          </div>
          <p className="mission-glance-meta">
            {report.complete ? "Complete" : "Incomplete"} · {endLabels[report.end_reason]}<br />
            {report.candidate_answers} candidate {report.candidate_answers === 1 ? "answer" : "answers"}{report.evaluated_by === "mock" && " · Mock mode, no AI evaluation"}
          </p>
        </div>
        {flags.length > 0 && (
          <div className="mission-integrity" role="note" aria-labelledby="integrity-heading">
            <p id="integrity-heading" className="mission-glance-label">Integrity flags ({flags.length}) · review the conversation</p>
            <ul>
              {flags.map((group) => (
                <li key={group.quote}>
                  <Icon glyph="⚠" tone="alert" />
                  <span>
                    <b>{group.labels.join(" · ")}</b>
                    {group.notes.map((note) => <span key={note} className="mission-integrity-note">{note}</span>)}
                    <blockquote>“{group.quote}”</blockquote>
                    <small>{group.detectedBy}</small>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mission-help">These requests were not followed and did not raise any score. They are recorded for a human to review, not as proof of bad faith.</p>
          </div>
        )}
        <div className="mission-glance-scores">
          <div className="mission-scorebar">
            <div className="mission-scorebar-head"><span>Answer quality</span><strong data-empty={score === null}>{score === null ? "Not enough to score" : `${score} / 100`}</strong></div>
            <div className="mission-scorebar-track" role="img" aria-label={score === null ? "Answer quality not scored" : `Answer quality ${score} of 100; interview threshold ${INTERVIEW_THRESHOLD}`}>
              {score !== null && <span className="mission-scorebar-fill" style={{ width: `${score}%` }} />}
              <span className="mission-scorebar-mark" style={{ left: `calc(${INTERVIEW_THRESHOLD}% - 1px)` }} />
            </div>
            <span className="mission-scorebar-note">Marker: interview threshold {INTERVIEW_THRESHOLD}</span>
          </div>
          <div className="mission-glance-stat">Correctness<strong>{report.correctness_score === null ? "n/a" : `${Math.round(report.correctness_score)}%`}</strong></div>
        </div>
        <div>
          <p className="mission-glance-label">Why this suggestion</p>
          <ul className="mission-glance-why">{report.next_step_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </div>
        <div className="mission-glance-groups">
          <GlanceGroup kind="strength" title="Strengths" items={groups.strengths} empty="None established in this screening." />
          <GlanceGroup kind="verify" title="Verify" items={groups.verify} empty="Nothing flagged." />
          <GlanceGroup kind="uncovered" title="Not covered" items={groups.uncovered} empty="Every topic came up." />
        </div>
        {report.summary && <p className="mission-glance-summary"><b>AI SUMMARY</b>{report.summary}</p>}
      </section>

      <section aria-labelledby="report-topics-heading">
        <h4 id="report-topics-heading">Job topics: resume → screening</h4>
        <ul className="mission-checklist">
          <li className="mission-checklist-head" aria-hidden="true"><span /><span>Topic</span><span>Resume</span><span>Screening</span></li>
          {topicsByCategory(report.topics).map((topic) => {
            const [glyph, tone] = topicIcon(topic);
            return (
              <li key={topic.requirement_id} data-check={topic.needs_check}>
                <Icon glyph={glyph} tone={tone} />
                <span className="mission-checklist-topic"><b>{plain(topic.description)}</b><small>{categoryLabels[topic.category]}</small></span>
                <span className="mission-checklist-resume"><span className="mission-checklist-caption">Resume: </span>{resumeLabels[topic.resume_status]}</span>
                <span className="mission-checklist-result">
                  <span className="mission-report-tags">
                    <span className="mission-tag">{statusLabels[topic.status]}</span>
                    {correctnessLabels[topic.correctness] && <span className="mission-tag">{correctnessLabels[topic.correctness]}</span>}
                    {topic.prompted && <span className="mission-tag">Needed a prompt</span>}
                    {topic.needs_check && <span className="mission-tag mission-tag-check">Needs check</span>}
                  </span>
                  {topic.note && <p>{topic.note}</p>}
                </span>
                <Quotes quotes={topic.quotes} />
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="report-dimensions-heading">
        <h4 id="report-dimensions-heading">How the answers were explained</h4>
        <div className="mission-dimension-strip">
          {report.dimensions.map((dimension) => {
            const [label] = dimensionLabels[dimension.name];
            return (
              <div key={dimension.name}>
                <b>{label}</b>
                <span className="mission-report-level" role="img" aria-label={dimension.level ? `${label}: level ${dimension.level} of 4` : `${label}: not assessed`}>
                  {[1, 2, 3, 4].map((step) => <i key={step} data-on={step <= dimension.level} />)}
                  <em>{dimension.level ? `${dimension.level}/4` : "Not assessed"}</em>
                </span>
              </div>
            );
          })}
        </div>
        <details className="mission-report-evidence">
          <summary><span className="mission-report-closed">Show reasons and quotes</span><span className="mission-report-open">Hide reasons and quotes</span></summary>
          <ul className="mission-report-dimensions">
            {report.dimensions.map((dimension) => {
              const [label, hint] = dimensionLabels[dimension.name];
              return (
                <li key={dimension.name}>
                  <div className="mission-report-row"><span><b>{label}</b><small>{hint}</small></span></div>
                  <p>{dimension.reason || "Not assessed: too little in the answers."}</p>
                  {dimension.quotes.length > 0 && <ul className="mission-report-quotes">{dimension.quotes.map((quote) => <li key={quote}><blockquote>“{quote}”</blockquote></li>)}</ul>}
                </li>
              );
            })}
          </ul>
        </details>
      </section>

      {asks.length > 0 && (
        <section aria-labelledby="report-ask-heading">
          <h4 id="report-ask-heading">Ask next</h4>
          <ol className="mission-asknext">{asks.map(({ question, topic }) => <li key={question}>{question}{topic && <small>{topic}</small>}</li>)}</ol>
        </section>
      )}

      <div className="mission-report-foot">
        <p className="mission-help">Not stored: this report is discarded when you close this panel, refresh or leave the page. Quotes are the candidate&apos;s unverified words and may contain speech-recognition errors.</p>
        <details>
          <summary>How this is scored</summary>
          <ul>
            <li>Only job-related content is judged; fluency, accent and manner never are.</li>
            <li>The AI chooses levels and statuses with the candidate&apos;s exact quotes; the server checks every quote and calculates all scores.</li>
            <li>Correctness credit: correct 1.0, after a hint 0.8, comparable equivalent 0.75, partly correct 0.5, incorrect 0. Experience questions have no right answer.</li>
            <li>Answer quality is the mean of the assessed dimensions and correctness. An interview is suggested at {INTERVIEW_THRESHOLD} or above with no mandatory gaps; incomplete screenings go to human review.</li>
            <li>These rules are illustrative, and a recruiter makes every decision.</li>
          </ul>
        </details>
      </div>
    </article>
  );
}
