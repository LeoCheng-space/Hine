"""Read-only deployment pre-checks used by build.sh.

subnets: compare `docker network inspect` JSON (stdin) with the pinned production subnets.
dns: compare `getent ahosts DOMAIN` output (stdin) with the approved VM IPv4 addresses.
Exit 0 when clear, 3 with one reason per stdout line otherwise.
"""
import ipaddress
import json
import sys


def subnet_conflicts(networks, project, edge, backend):
    wanted = {"edge": ipaddress.IPv4Network(edge), "backend": ipaddress.IPv4Network(backend)}
    problems = []
    for network in networks:
        name = network.get("Name") or "?"
        labels = network.get("Labels") or {}
        current = []
        for item in (network.get("IPAM") or {}).get("Config") or []:
            if item and item.get("Subnet"):
                parsed = ipaddress.ip_network(item["Subnet"], strict=False)
                if parsed.version == 4:
                    current.append(parsed)
        role = labels.get("com.docker.compose.network")
        if labels.get("com.docker.compose.project") == project and role in wanted:
            if current != [wanted[role]]:
                shown = ",".join(str(subnet) for subnet in current) or "未知"
                problems.append(f"本部署的 {name} 網路已存在，子網路為 {shown}，但 deploy.env 設定為 {wanted[role]}；"
                                "變更子網路需先停止服務並手動移除該網路（build.sh 不會刪除網路）")
            continue
        for subnet in current:
            for role_name, target in wanted.items():
                if subnet.overlaps(target):
                    problems.append(f"Docker 網路 {name} 的子網路 {subnet} 與 deploy.env 的 {role_name} 子網路 {target} 重疊；"
                                    "請在 deploy.env 改用其他私有網段")
    return problems


def dns_mismatch(getent_output, expected_text):
    expected = {str(ipaddress.ip_address(part.strip())) for part in expected_text.split(",")}
    actual = set()
    for line in getent_output.splitlines():
        fields = line.split()
        if fields:
            actual.add(str(ipaddress.ip_address(fields[0])))
    if not actual:
        return "無法解析網域（沒有任何 DNS 紀錄）"
    if actual != expected:
        return (f"DNS 解析結果 {', '.join(sorted(actual))} 與 HINE_EXPECTED_IP {', '.join(sorted(expected))} 不一致"
                "（不得有其他 A 紀錄或任何 AAAA 紀錄）")
    return None


def main(argv):
    if len(argv) == 4 and argv[0] == "subnets":
        problems = subnet_conflicts(json.load(sys.stdin), argv[1], argv[2], argv[3])
    elif len(argv) == 2 and argv[0] == "dns":
        message = dns_mismatch(sys.stdin.read(), argv[1])
        problems = [message] if message else []
    else:
        print("用法：deploy-checks.py subnets PROJECT EDGE BACKEND | dns EXPECTED_IPS", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem)
    return 3 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
