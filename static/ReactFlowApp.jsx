const { useState, useCallback, useEffect } = React;
const { ReactFlow, Controls, Background, applyNodeChanges, applyEdgeChanges, addEdge, Handle, Position } = window.ReactFlow;

// --- Dữ liệu ban đầu từ Jinja ---
const initParticipants = window.__INITIAL_PARTICIPANTS__ || [];

// --- COMPONENTS CƠ BẢN ---
const RoleSlotNode = ({ data, id }) => {
  // data: { label: 'Chủ đất', role: 'Owner', person: null, type: 'input'|'output'|'default' }
  const isOccupied = !!data.person;

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const personStr = e.dataTransfer.getData('application/json');
    if (!personStr) return;
    try {
      const person = JSON.parse(personStr);
      data.onAssign(id, person);
    } catch(err) {
      console.error(err);
    }
  };

  const handleRemove = (e) => {
    e.stopPropagation();
    data.onAssign(id, null);
  }

  // Define Handles based on role
  // Owner is center. Parents are above (target). Children are below (source).
  return (
    <div 
      style={{
        padding: 10,
        borderRadius: 8,
        background: isOccupied ? '#fdf8e4' : '#f3f4f6',
        border: `2px ${isOccupied ? 'solid #d97706' : 'dashed #9ca3af'}`,
        minWidth: 150,
        textAlign: 'center',
        position: 'relative'
      }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {data.handles.includes('target') && <Handle type="target" position={Position.Top} />}
      {data.handles.includes('left') && <Handle type="target" position={Position.Left} id="left" />}
      {data.handles.includes('right') && <Handle type="source" position={Position.Right} id="right" />}
      
      <div style={{ fontSize: 12, fontWeight: 'bold', color: '#6b7280', marginBottom: 5 }}>
        {data.label}
      </div>
      
      {!isOccupied ? (
        <div style={{ fontSize: 12, color: '#9ca3af' }}>Thả người vào đây...</div>
      ) : (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 5, marginTop: 5 }}>
          <div style={{ fontWeight: 'bold', fontSize: 14 }}>{data.person.name}</div>
          <div style={{ fontSize: 11, color: '#6b7280' }}>{data.person.doc || '---'}</div>
          <button 
            onClick={handleRemove}
            style={{ position: 'absolute', top: -10, right: -10, background: '#ef4444', color: 'white', border: 'none', borderRadius: '50%', width: 24, height: 24, cursor: 'pointer' }}
          >
            ×
          </button>
        </div>
      )}

      {data.handles.includes('source') && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
};

const nodeTypes = { roleSlot: RoleSlotNode };

// --- MAIN APP COMPONENT ---
function FamilyTreeApp() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);

  // Hàm cập nhật person cho 1 node cụ thể
  const onAssignPerson = useCallback((nodeId, person) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === nodeId) {
          // Check if person is valid for this role (add logic if needed)
          return { ...node, data: { ...node.data, person } };
        }
        return node;
      })
    );
  }, []);

  // Thiết lập cây Mặc định cho Hồ sơ thừa kế cơ bản
  useEffect(() => {
    const initialNodes = [
      { id: 'father', type: 'roleSlot', position: { x: 200, y: 50 }, data: { label: 'Cha ruột', role: 'Cha', person: null, handles: ['source'], onAssign: onAssignPerson } },
      { id: 'mother', type: 'roleSlot', position: { x: 700, y: 50 }, data: { label: 'Mẹ ruột', role: 'Mẹ', person: null, handles: ['source'], onAssign: onAssignPerson } },
      { id: 'owner', type: 'roleSlot', position: { x: 450, y: 300 }, data: { label: 'CHỦ ĐẤT', role: 'Owner', person: null, handles: ['target', 'source', 'right'], onAssign: onAssignPerson } },
      { id: 'spouse', type: 'roleSlot', position: { x: 950, y: 300 }, data: { label: 'Vợ/Chồng', role: 'Vợ/Chồng', person: null, handles: ['left'], onAssign: onAssignPerson } },
      // Một node Con mẫu
      { id: 'child_1', type: 'roleSlot', position: { x: 450, y: 550 }, data: { label: 'Con ruột', role: 'Con', person: null, handles: ['target', 'source'], onAssign: onAssignPerson } },
    ];

    const initialEdges = [
      { id: 'e-father-owner', source: 'father', target: 'owner', animated: true },
      { id: 'e-mother-owner', source: 'mother', target: 'owner', animated: true },
      { id: 'e-owner-spouse', source: 'owner', sourceHandle: 'right', target: 'spouse', targetHandle: 'left', animated: true, type: 'step' },
      { id: 'e-owner-child1', source: 'owner', target: 'child_1', animated: true },
    ];

    // Load existing participants into nodes
    if (initParticipants && initParticipants.length > 0) {
      initParticipants.forEach(p => {
        const matchingNode = initialNodes.find(n => n.data.role === p.role && !n.data.person);
        if (matchingNode) {
          matchingNode.data.person = p;
        }
      });
    }

    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [onAssignPerson]);

  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  
  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    []
  );

  const addExtraChild = () => {
    const newId = `child_${Date.now()}`;
    const childNodesCount = nodes.filter(n => n.id.startsWith('child_')).length;
    const newNode = {
      id: newId,
      type: 'roleSlot',
      position: { x: 450 + (childNodesCount * 300), y: 550 },
      data: { label: 'Con ruột', role: 'Con', person: null, handles: ['target', 'source'], onAssign: onAssignPerson }
    };
    const newEdge = { id: `e-owner-${newId}`, source: 'owner', target: newId, animated: true };
    setNodes((nds) => [...nds, newNode]);
    setEdges((eds) => [...eds, newEdge]);
  };

  // Đồng bộ Dữ liệu Cây vào Form gốc để Submit/Preview được
  useEffect(() => {
    // Collect all assigned persons
    const assigned = nodes.filter(n => n.data.person).map(n => ({
      ...n.data.person,
      role: n.data.role
    }));
    
    // Đẩy payload ra window để hàm loadLivePreview lấy được
    window.__CURRENT_TREE_PAYLOAD__ = assigned;
  }, [nodes]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>

      {/* Toolbar */}
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 10, display: 'flex', gap: 10 }}>
        <button onClick={addExtraChild} style={{ padding: '5px 10px', background: 'white', border: '1px solid #ccc', borderRadius: 4, cursor: 'pointer' }}>
          + Thêm Con
        </button>
      </div>
    </div>
  );
}

// Render component
const root = ReactDOM.createRoot(document.getElementById('react-flow-root'));
root.render(<FamilyTreeApp />);
