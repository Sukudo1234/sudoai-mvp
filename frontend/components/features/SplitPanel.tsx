"use client";
import { useState } from "react";
import TusUploader from "../TusUploader";
import { createSplit, getJob } from "@/app/lib/api";

export default function SplitPanel() {
  const [files, setFiles] = useState<{name:string; tusUrl:string}[]>([]);
  const [jobs, setJobs] = useState<{id:string; name:string; state:string; result?:any}[]>([]);

  const onUploaded = (info: { tusUrl: string; name: string }) => {
    setFiles((s) => [...s, { name: info.name, tusUrl: info.tusUrl }]);
  };

  async function run() {
    const created = await Promise.all(files.map(f => createSplit(f.tusUrl).then(x => ({...f, id:x.task_id}))));
    setJobs(created.map(c => ({id:c.id, name:c.name, state:"PENDING"})));

    // poll
    for (const c of created) {
      (async () => {
        while (true) {
          const s = await getJob(c.id);
          if (s.state === "SUCCESS") { setJobs(j => j.map(k => k.id===c.id ? {...k, state:s.state, result:s.result} : k)); break; }
          if (s.state === "FAILURE") { setJobs(j => j.map(k => k.id===c.id ? {...k, state:s.state, result:{error:s.error}} : k)); break; }
          await new Promise(r => setTimeout(r, 1200));
        }
      })();
    }
  }

  return (
    <div className="space-y-4">
      <TusUploader multiple onUploaded={onUploaded} />
      <button onClick={run} className="px-4 py-2 rounded-xl bg-indigo-600 text-white">Split with Demucs</button>
      <div className="space-y-2">
        {jobs.map(j => (
          <div key={j.id} className="p-3 rounded-lg border">
            <div className="font-medium">{j.name}</div>
            <div className="text-sm">Status: {j.state}</div>
            {j.result?.results && (
              <div className="text-sm mt-2">
                {Object.entries(j.result.results).map(([stem, v]: any) => (
                  <div key={stem}><b>{stem}</b>: <a className="underline" href={v.url} target="_blank">download</a></div>
                ))}
              </div>
            )}
            {j.result?.error && <div className="text-red-600 text-sm mt-2">{String(j.result.error)}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
