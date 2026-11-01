import assert from "node:assert/strict";
import { test } from "node:test";
import { containerFromAuthority, hostFromAuthority, portFromAuthority, sshPort } from "../src/remoteHost";

const hex = (o: object) => Buffer.from(JSON.stringify(o)).toString("hex");

test("plain Remote-SSH authorities name the host", () => {
  assert.equal(hostFromAuthority("ssh-remote+build-server"), "build-server");
  assert.equal(hostFromAuthority("ssh-remote+build-server.example.com"), "build-server.example.com");
});

test("hex-encoded authorities are decoded", () => {
  assert.equal(hostFromAuthority("ssh-remote+" + hex({ hostName: "GpuBox" })), "GpuBox");
  assert.equal(hostFromAuthority("ssh-remote+" + hex({ hostName: "gpu-box", user: "alice" })), "alice@gpu-box");
  assert.equal(hostFromAuthority("ssh-remote+" + hex({ hostName: "gpu-box", port: 2222 })), "gpu-box");
});

// A port typed into Remote-SSH's connect box: ssh <host> may not go there
test("the port a window reached its host on, when one was given", () => {
  assert.equal(portFromAuthority("ssh-remote+" + hex({ hostName: "gpu-box", user: "alice", port: 2222 })), 2222);
  assert.equal(portFromAuthority("ssh-remote+" + hex({ hostName: "gpu-box", port: "2200" })), 2200);
  assert.equal(portFromAuthority("ssh-remote+" + hex({ hostName: "gpu-box" })), undefined);
  assert.equal(portFromAuthority("ssh-remote+build-server"), undefined);
  assert.equal(portFromAuthority("wsl+Ubuntu"), undefined);
  assert.equal(sshPort("talpy-den-test.invalid"), 22, "ssh's own port, nothing connected");
});

test("other remotes and odd names are not SSH hosts", () => {
  assert.equal(hostFromAuthority(undefined), undefined);
  assert.equal(hostFromAuthority("wsl+Ubuntu"), undefined);
  assert.equal(hostFromAuthority("dev-container+abc"), undefined);
  assert.equal(hostFromAuthority("ssh-remote+bad name;rm"), undefined);
});

test("a Dev Containers window's container, as remote.py names it", () => {
  const known = [
    { id: "podman:shop", engine: "podman", name: "shop", folder: "/home/me/shop", cid: "ab".repeat(32) },
    { id: "docker:api@lab", engine: "docker", name: "api", folder: "/srv/api", host: "lab" },
  ];
  const attached = (name: string) => "attached-container+" + hex({ containerName: "/" + name });
  // its name (listed: the listing's engine, though Dev Containers runs "docker")
  assert.equal(containerFromAuthority(attached("shop"), known), "podman:shop");
  // not listed: Dev Containers' engine
  assert.equal(containerFromAuthority(attached("new-one"), known, "/usr/bin/podman"), "podman:new-one");
  assert.equal(containerFromAuthority(attached("new-one"), known), "docker:new-one");
  // its id
  assert.equal(containerFromAuthority("attached-container+" + Buffer.from("ab".repeat(6)).toString("hex"), known), "podman:shop");
  // a dev container: its project folder
  assert.equal(containerFromAuthority("dev-container+" + hex({ hostPath: "/home/me/shop", configFile: {} }), known), "podman:shop");
  assert.equal(containerFromAuthority("dev-container+" + hex({ hostPath: "/elsewhere" }), known), "");
  // through Remote-SSH: one on that host
  assert.equal(containerFromAuthority(attached("api") + "@ssh-remote+lab", known), "docker:api@lab");
  assert.equal(containerFromAuthority(attached("api"), known), "docker:api");
  // not a container window
  assert.equal(containerFromAuthority("ssh-remote+lab", known), undefined);
  assert.equal(containerFromAuthority(undefined, known), undefined);
});
