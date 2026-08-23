import { useMemo } from "react";
import { useStudio } from "../store.js";
import { AGENTS } from "../sim/agents.js";
import AgentDesk from "../studio/AgentDesk.jsx";
import ApprovalScreen from "../studio/ApprovalScreen.jsx";
import LudoTable from "../ludo/LudoTable.jsx";
import RoomShell from "./RoomShell.jsx";
import Lighting from "./Lighting.jsx";
import CameraRig, { pointer } from "./CameraRig.jsx";
import { deskPose, APPROVAL_POS, APPROVAL_ROT } from "./layout.js";

export default function Scene({ ludo }) {
  const theme = useStudio((s) => s.theme);
  const focus = useStudio((s) => s.focus);
  const interacted = useStudio((s) => s.interacted);
  const agents = useStudio((s) => s.agents);
  const stage = useStudio((s) => s.stage);
  const approval = useStudio((s) => s.approval);
  const { focusDesk, focusTable, focusApproval, markInteracted, answerApproval } = useStudio.getState();

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
      <Lighting lightMode={lightMode} />
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
