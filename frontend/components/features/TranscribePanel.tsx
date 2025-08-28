"use client";
import { useState } from "react";
import TusUploader from "../TusUploader";
import { createTranscribe, getJob } from "@/app/lib/api";

export default function TranscribePanel() {
  const [file, setFile] = useState<{name:string; tusUrl:string} | null>(null);
  const [job, setJob] = useState<any>(null);

  return (
    <div className="space-y-4">
      <TusUploader multiple={false} onUploaded={(f)=>setFile({name:f.name, tusUrl:f.tusUrl})}/>
      <button
        disabled={!file}
        onClick={async ()=>{
          const { task_id } = await createTranscribe(file!.tusUrl);
          setJob({ id: task_id, state: "PENDING" });
          while (true) {
            const s = await getJob(task_id);
            if (s.state !== "PENDING" && s.state !== "STARTED") { setJob({ id: task_id, state: s.state, result: s.result }); break; }
            await new Promise(r => setTimeout(r, 1200));
          }
        }}
        className="px-4 py-2 rounded-xl bg-indigo-600 text-white disabled:opacity-60"
      >
        Transcribe
      </button>

      {job?.result?.srt?.url && (
        <div className="p-3 rounded-lg border">
          <div>Status: {job.state}</div>
          <a className="underline" href={job.result.srt.url} target="_blank">Download .srt</a>
          {job.result.warning && <div className="text-amber-600 text-sm mt-2">{job.result.warning}</div>}
        </div>
      )}
    </div>
  );
}
