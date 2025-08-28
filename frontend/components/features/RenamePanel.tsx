"use client";
import { useState } from "react";
import { bulkRename, getJob } from "@/app/lib/api";

export default function RenamePanel() {
  const [keysText, setKeysText] = useState("");
  const [pattern, setPattern] = useState("SERIES_{basename}_EP-{index}{ext}");
  const [job, setJob] = useState<any>(null);

  return (
    <div className="space-y-4">
      <textarea className="w-full h-32 border rounded-lg p-2" placeholder="One S3 key per line (from results)" value={keysText} onChange={e=>setKeysText(e.target.value)} />
      <input className="w-full border rounded-lg p-2" value={pattern} onChange={e=>setPattern(e.target.value)} />
      <button
        onClick={async ()=>{
          const keys = keysText.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
          const { task_id } = await bulkRename(keys, pattern, 1, 2, false);
          setJob({ id: task_id, state: "PENDING" });
          while (true) {
            const s = await getJob(task_id);
            if (s.state !== "PENDING" && s.state !== "STARTED") { setJob({ id: task_id, state: s.state, result: s.result }); break; }
            await new Promise(r => setTimeout(r, 1000));
          }
        }}
        className="px-4 py-2 rounded-xl bg-indigo-600 text-white"
      >Rename</button>

      {job?.result && (
        <div className="text-sm p-3 border rounded-lg">
          {job.result.mapping?.map((m:any, i:number)=>(
            <div key={i}>{m.from} → <b>{m.to}</b></div>
          ))}
        </div>
      )}
    </div>
  );
}
