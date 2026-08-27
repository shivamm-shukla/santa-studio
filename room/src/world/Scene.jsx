import { useMemo } from "react";
import { useStudio } from "../store.js";
import { AGENTS } from "../sim/agents.js";
import AgentDesk from "../studio/AgentDesk.jsx";
import ApprovalScreen from "../studio/ApprovalScreen.jsx";
import LudoTable from "../ludo/LudoTable.jsx";
import VocalBooth from "../studio/VocalBooth.jsx";
import CommissionBoard from "../studio/CommissionBoard.jsx";
import VoiceRack from "../studio/VoiceRack.jsx";
import CuttingBench from "../studio/CuttingBench.jsx";
import RoomShell from "./RoomShell.jsx";
import Lighting from "./Lighting.jsx";
import CameraRig, { pointer } from "./CameraRig.jsx";
import {
  deskPose,
  APPROVAL_POS,
  APPROVAL_ROT,
  BOARD_POS,
  BOARD_ROT,
  BOOTH_POS,
  BOOTH_ROT,
  RACK_POS,
  RACK_ROT,
  BENCH_POS,
  BENCH_ROT,
  placePosition,
} from "./layout.js";

export default function Scene({ ludo, mic, commission, voices, bench }) {
  const theme = useStudio((s) => s.theme);
  const focus = useStudio((s) => s.focus);
  const interacted = useStudio((s) => s.interacted);
  const agents = useStudio((s) => s.agents);
  const stage = useStudio((s) => s.stage);
  const filming = useStudio((s) => s.filming);
  const lightLevel = useStudio((s) => s.lightLevel);
  const demoing = useStudio((s) => s.demoing);
  const approval = useStudio((s) => s.approval);
  const { focusDesk, focusTable, focusApproval, focusBooth, focusBoard, focusRack, focusBench, markInteracted, answerApproval } =
    useStudio.getState();

  const lightMode = theme === "light";

  // What the Manager's own screen shows: the run board, everyone's status.
  const roster = useMemo(() => {
    const list = AGENTS.filter((a) => a.state).map((a) => ({
      name: a.name,
      status: agents[a.id].status,
    }));
    return { list, version: list.map((a) => a.status[0]).join("") };
  }, [agents]);

  // A drag that ends over a desk is a look-around, not a click on the desk.
  const guard = (fn) => (...args) => {
    if (pointer.dragged) return;
    fn(...args);
  };

  return (
    <>
      <CameraRig focus={focus} interacted={interacted} onInteract={markInteracted} />
      <Lighting lightMode={lightMode} at={placePosition(focus)} photo={!!focus.photo} film={filming} level={lightLevel} />
      <RoomShell />

      {AGENTS.map((agent, i) => {
        const pose = deskPose(i);
        return (
          <group key={agent.id} position={pose.position} rotation={[0, pose.rotationY, 0]}>
            <AgentDesk
              agent={agent}
              agentState={agents[agent.id]}
              roster={roster}
              stage={stage}
              focused={focus.kind === "desk" && focus.id === agent.id}
              lightMode={lightMode}
              showPlate={focus.kind === "room"}
              onSelect={guard(focusDesk)}
            />
          </group>
        );
      })}

      <LudoTable ludo={ludo} focused={focus.kind === "table"} onSelect={guard(focusTable)} />

      <CommissionBoard
        position={BOARD_POS}
        rotation={BOARD_ROT}
        brief={commission.brief}
        live={commission.live}
        focused={focus.kind === "board"}
        onSelect={guard(focusBoard)}
      />

      <VocalBooth
        position={BOOTH_POS}
        rotation={BOOTH_ROT}
        mic={mic}
        focused={focus.kind === "booth"}
        lightMode={lightMode}
        onSelect={guard(focusBooth)}
        onPress={guard(() => {
          // One button, and what it does follows from where you are: turn the
          // mic on, start, stop, or go again.
          //
          // Stop used to be gated on having recorded the eight seconds a clone
          // needs, so pressing it early did nothing at all - and the only
          // thing that would have explained why is a screen on a wall you are
          // not facing while you talk into the microphone. Pressing stop stops
          // it; whether the take is long enough is a question for afterwards,
          // where it can be answered in words.
          if (!mic) return;
          if (mic.status === "idle" || mic.status === "denied") mic.connect();
          else if (mic.status === "ready") mic.start();
          else if (mic.status === "recording") mic.stop();
          else if (mic.status === "recorded") mic.again();
        })}
      />

      <VoiceRack
        position={RACK_POS}
        rotation={RACK_ROT}
        voices={voices.voices}
        order={voices.order}
        selected={voices.selected}
        focused={focus.kind === "rack"}
        onSelect={guard(focusRack)}
      />

      <CuttingBench
        position={BENCH_POS}
        rotation={BENCH_ROT}
        project={bench?.project}
        selected={bench?.selected}
        /* The set goes quiet only when nothing is being laid into it. In the
           demo the app is on the glass, so it should behave exactly as it
           does for a person standing there; in the short reel there is no
           flat layer at all, and a quiet screen would be a dark rectangle in
           the shot where the product should be. */
        focused={focus.kind === "bench" && (demoing || !filming)}
        onSelect={guard(focusBench)}
      />

      <ApprovalScreen
        position={APPROVAL_POS}
        rotation={[0, APPROVAL_ROT, 0]}
        request={approval}
        stage={stage}
        onAnswer={guard(answerApproval)}
        onSelect={guard(focusApproval)}
      />
    </>
  );
}
