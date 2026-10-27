"use client";

import type { AvailabilityInput, NoticeStatus } from "@/lib/availability";

const options: { value: NoticeStatus | ""; label: string }[] = [
  { value: "", label: "Not provided" },
  { value: "immediate", label: "Available now" },
  { value: "serving_notice", label: "Serving notice period" },
  { value: "not_serving", label: "Not yet serving notice" },
];

/** Optional, self-reported notice details for one temporary upload. */
export function AvailabilityFields({ id, value, onChange }: { id: string; value: AvailabilityInput; onChange: (value: AvailabilityInput) => void }) {
  function setStatus(status: string) {
    onChange({ status: status === "" ? null : (status as NoticeStatus), last_working_day: null, notice_days: status === "not_serving" ? 30 : null });
  }
  return <fieldset className="mission-fieldset">
    <legend>Availability <small>optional</small></legend>
    <label htmlFor={`${id}-status`}>Notice status</label>
    <select id={`${id}-status`} value={value.status ?? ""} onChange={(event) => setStatus(event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
    {value.status === "serving_notice" && <><label htmlFor={`${id}-lwd`}>Last working day</label>
      <input id={`${id}-lwd`} type="date" required value={value.last_working_day ?? ""} onChange={(event) => onChange({ ...value, last_working_day: event.target.value || null })} /></>}
    {value.status === "not_serving" && <><label htmlFor={`${id}-days`}>Notice period (days)</label>
      <input id={`${id}-days`} type="number" min={0} max={365} step={1} required value={value.notice_days ?? ""} onChange={(event) => onChange({ ...value, notice_days: event.target.value === "" ? null : Math.max(0, Math.min(365, Math.trunc(Number(event.target.value)))) })} /></>}
    <p className="mission-help">A shorter time to join adds a small ranking bonus (at most +5). Not provided never lowers a candidate. The match score itself is unchanged.</p>
  </fieldset>;
}

/** Incomplete details are sent as not provided rather than guessed. */
export function completeAvailability(value: AvailabilityInput): AvailabilityInput {
  if (value.status === "serving_notice" && !value.last_working_day) return { status: null, last_working_day: null, notice_days: null };
  if (value.status === "not_serving" && value.notice_days === null) return { status: null, last_working_day: null, notice_days: null };
  return value;
}
