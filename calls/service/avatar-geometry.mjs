import { Vector3 } from 'three';

export function removeOutlinePasses(root) {
  root.traverse(mesh => {
    if (!mesh.isMesh || !Array.isArray(mesh.material)) return;
    const originals = mesh.material, keep = originals.filter(material => !material.isOutline);
    if (keep.length === originals.length) return;
    const groups = mesh.geometry.groups.filter(group => !originals[group.materialIndex]?.isOutline);
    mesh.geometry.clearGroups();
    for (const group of groups) mesh.geometry.addGroup(group.start, group.count, keep.indexOf(originals[group.materialIndex]));
    mesh.material = keep;
    for (const material of originals) if (material.isOutline) material.dispose();
  });
}

// This camera shows head, shoulders and chest. Omit the lower-body triangles
// that remain below the view, with generous room for idle head/body movement.
export function trimLowerBody(vrm) {
  vrm.update(0); vrm.scene.updateMatrixWorld(true);
  const vertex = new Vector3();
  const floor = vrm.humanoid.getNormalizedBoneNode('head').getWorldPosition(vertex).y - 0.6;
  let removed = 0;
  vrm.scene.traverse(mesh => {
    if (!mesh.isSkinnedMesh || !mesh.geometry.index) return;
    const geometry = mesh.geometry, original = geometry.index;
    const heights = new Float32Array(geometry.attributes.position.count);
    for (let i = 0; i < heights.length; i++) heights[i] = mesh.getVertexPosition(i, vertex).applyMatrix4(mesh.matrixWorld).y;
    const grouped = geometry.groups.length > 0;
    const groups = grouped ? geometry.groups.map(group => ({ ...group })) : [{ start: 0, count: original.count, materialIndex: 0 }];
    const indices = []; geometry.clearGroups();
    for (const group of groups) {
      const start = indices.length;
      for (let i = group.start; i < group.start + group.count; i += 3) {
        const a = original.getX(i), b = original.getX(i + 1), c = original.getX(i + 2);
        if (heights[a] < floor && heights[b] < floor && heights[c] < floor) removed++;
        else indices.push(a, b, c);
      }
      if (grouped) geometry.addGroup(start, indices.length - start, group.materialIndex);
    }
    geometry.setIndex(indices);
    if (indices.length === 0) mesh.layers.disable(0);
  });
  return removed;
}
