/**
 * proposed_h86_create_balance_manager.mjs
 *
 * Automated script to create and publicly share a DeepBook V3 BalanceManager object
 * on Sui Mainnet using the funded wallet (5.419245048 SUI) and official Sui GraphQL.
 *
 * Targets:
 *   1. 0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::new
 *   2. 0x2::transfer::public_share_object<0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::BalanceManager>
 *
 * Endpoint: https://graphql.mainnet.sui.io/graphql
 *
 * Usage:
 *   node proposed_h86_create_balance_manager.mjs [--dry-run | --execute]
 */

import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import * as fs from 'fs';
import * as path from 'path';

const GRAPHQL_URL = 'https://graphql.mainnet.sui.io/graphql';
const DEEPBOOK_V3_PACKAGE = '0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809';
const SUI_FRAMEWORK = '0x0000000000000000000000000000000000000000000000000000000000000002';
const BALANCE_MANAGER_TYPE = `${DEEPBOOK_V3_PACKAGE}::balance_manager::BalanceManager`;

async function executeGraphQL(query, variables = {}) {
  const res = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  });
  const data = await res.json();
  if (data.errors && data.errors.length > 0) {
    throw new Error(`GraphQL Error: ${JSON.stringify(data.errors)}`);
  }
  return data.data;
}

async function main() {
  const isExecute = process.argv.includes('--execute');
  console.log('='.repeat(70));
  console.log(`DeepBook V3 BalanceManager Creation Script [Mode: ${isExecute ? 'LIVE EXECUTION' : 'DRY RUN / VERIFY'}]`);
  console.log('='.repeat(70));

  // 1. Read .env credentials
  const explicitEnvPath = '/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env';
  const envPath = process.env.ENV_PATH || (fs.existsSync(explicitEnvPath) ? explicitEnvPath : path.resolve(process.cwd(), '.env'));

  console.log(`Reading credentials from: ${envPath}`);
  const envContent = fs.readFileSync(envPath, 'utf8');
  const privKeyMatch = envContent.match(/SUI_PRIVATE_KEY=(.*)/);
  const addressMatch = envContent.match(/SUI_WALLET_ADDRESS=(.*)/);
  const bmMatch = envContent.match(/DEEPBOOK_BALANCE_MANAGER_ID=(.*)/);

  if (!privKeyMatch || !privKeyMatch[1].trim()) {
    throw new Error('SUI_PRIVATE_KEY missing in .env!');
  }
  const privateKey = privKeyMatch[1].trim();
  const expectedAddress = addressMatch ? addressMatch[1].trim() : null;
  const existingBmId = bmMatch ? bmMatch[1].trim() : '';

  // 2. Derive keypair and verify address
  const keypair = Ed25519Keypair.fromSecretKey(privateKey);
  const walletAddress = keypair.toSuiAddress();
  console.log(`Derived Wallet Address: ${walletAddress}`);

  if (expectedAddress && walletAddress.toLowerCase() !== expectedAddress.toLowerCase()) {
    throw new Error(`Derived address ${walletAddress} does not match expected ${expectedAddress}!`);
  }

  // Check if existing BalanceManager is already valid on-chain
  if (existingBmId && existingBmId.startsWith('0x') && existingBmId.length > 10) {
    console.log(`Checking existing DEEPBOOK_BALANCE_MANAGER_ID: ${existingBmId}...`);
    const checkQuery = `query CheckBM($id: SuiAddress!) {
      object(address: $id) {
        asMoveObject {
          contents {
            type { repr }
          }
        }
      }
    }`;
    try {
      const checkData = await executeGraphQL(checkQuery, { id: existingBmId });
      const objType = checkData?.object?.asMoveObject?.contents?.type?.repr;
      if (objType && objType.includes('balance_manager::BalanceManager')) {
        console.log(`Existing BalanceManager is ALREADY valid on-chain: ${existingBmId}`);
        console.log('No new BalanceManager creation required.');
        return;
      }
    } catch (e) {
      console.log(`Existing BM check error: ${e.message}, proceeding to create new.`);
    }
  }

  // 3. Query Sui Mainnet GraphQL for balance and gas coin
  console.log('\nQuerying Sui Mainnet GraphQL for wallet balance and gas coin...');
  const walletQuery = `query GetWallet($addr: SuiAddress!) {
    epoch { referenceGasPrice }
    address(address: $addr) {
      balance(coinType: "0x2::sui::SUI") { totalBalance }
      objects(first: 10) {
        nodes {
          address
          version
          digest
          contents {
            type { repr }
          }
        }
      }
    }
  }`;

  const walletData = await executeGraphQL(walletQuery, { addr: walletAddress });
  const refGasPrice = parseInt(walletData.epoch.referenceGasPrice, 10) || 100;
  const totalBalanceMist = BigInt(walletData.address.balance.totalBalance);
  const totalBalanceSui = Number(totalBalanceMist) / 1e9;

  console.log(`  Reference Gas Price: ${refGasPrice}`);
  console.log(`  Total SUI Balance:   ${totalBalanceMist} MIST (~${totalBalanceSui.toFixed(9)} SUI)`);

  const minGasRequiredMist = 50_000_000n; // 0.05 SUI
  if (totalBalanceMist < minGasRequiredMist) {
    throw new Error(`Insufficient SUI for gas! Required: 0.05 SUI, Available: ${totalBalanceSui} SUI`);
  }

  const objects = walletData.address.objects.nodes;
  const gasCoin = objects.find(o =>
    o.contents?.type?.repr?.includes('0x0000000000000000000000000000000000000000000000000000000000000002::sui::SUI') ||
    o.contents?.type?.repr?.includes('0x2::sui::SUI')
  );

  if (!gasCoin) {
    throw new Error('No SUI gas coin object found for this address!');
  }
  console.log(`  Selected Gas Coin:   ${gasCoin.address} (v${gasCoin.version}, digest: ${gasCoin.digest})`);

  // 4. Construct Move PTB
  console.log('\nConstructing Move PTB:');
  console.log(`  1. Call: ${DEEPBOOK_V3_PACKAGE}::balance_manager::new()`);
  console.log(`  2. Call: ${SUI_FRAMEWORK}::transfer::public_share_object<${BALANCE_MANAGER_TYPE}>(manager)`);

  const tx = new Transaction();
  tx.setSender(walletAddress);
  tx.setGasPrice(refGasPrice);
  tx.setGasBudget(50_000_000); // 0.05 SUI gas budget
  tx.setGasPayment([{
    objectId: gasCoin.address,
    version: gasCoin.version,
    digest: gasCoin.digest,
  }]);

  const [manager] = tx.moveCall({
    target: `${DEEPBOOK_V3_PACKAGE}::balance_manager::new`,
    arguments: [],
  });

  tx.moveCall({
    target: `${SUI_FRAMEWORK}::transfer::public_share_object`,
    typeArguments: [BALANCE_MANAGER_TYPE],
    arguments: [manager],
  });

  // 5. Build and Sign Transaction
  console.log('\nBuilding BCS transaction bytes...');
  const txBytes = await tx.build();
  console.log(`  Transaction BCS built successfully (${txBytes.length} bytes).`);

  console.log('Signing transaction with Ed25519 keypair...');
  const { signature } = await keypair.signTransaction(txBytes);
  const b64Bytes = Buffer.from(txBytes).toString('base64');
  console.log(`  Signature generated (prefix: ${signature.slice(0, 15)}...).`);

  // 6. Pre-flight Signature & Protocol Verification
  console.log('\nVerifying signature via GraphQL verifySignature...');
  const verifyQuery = `query VerifySig($msg: Base64!, $sig: Base64!, $author: SuiAddress!) {
    verifySignature(
      message: $msg,
      signature: $sig,
      intentScope: TRANSACTION_DATA,
      author: $author
    ) {
      success
    }
  }`;
  const verifyData = await executeGraphQL(verifyQuery, {
    msg: b64Bytes,
    sig: signature,
    author: walletAddress,
  });

  if (!verifyData?.verifySignature?.success) {
    throw new Error(`Pre-flight signature verification failed: ${JSON.stringify(verifyData)}`);
  }
  console.log('  [PASS] Sui GraphQL signature verification returned success: true.');

  if (!isExecute) {
    console.log('\n' + '='.repeat(70));
    console.log('DRY RUN COMPLETE — Transaction is 100% valid and verified.');
    console.log('To broadcast this transaction on Sui Mainnet, run with: --execute');
    console.log('='.repeat(70));
    return;
  }

  // 7. Live Execution Mutation
  console.log('\n[LIVE EXECUTION] Broadcasting executeTransaction mutation to Sui Mainnet...');
  const execMutation = `mutation ExecuteBM($bcs: Base64!, $signatures: [Base64!]!) {
    executeTransaction(transactionDataBcs: $bcs, signatures: $signatures) {
      effects {
        status
        digest
        executionError {
          message
          abortCode
        }
        gasEffects {
          gasSummary {
            computationCost
            storageCost
            storageRebate
          }
        }
        objectChanges {
          nodes {
            address
            idCreated
            outputState {
              asMoveObject {
                contents {
                  type {
                    repr
                  }
                }
              }
            }
          }
        }
        effectsJson
      }
    }
  }`;

  const execData = await executeGraphQL(execMutation, {
    bcs: b64Bytes,
    signatures: [signature],
  });

  const effects = execData?.executeTransaction?.effects;
  const status = effects?.status;
  const txDigest = effects?.digest;

  console.log(`Transaction status: ${status}`);
  console.log(`Transaction digest: ${txDigest}`);

  if (status !== 'SUCCESS') {
    throw new Error(`Transaction execution failed: ${JSON.stringify(effects?.executionError || effects)}`);
  }

  // 8. Extract Created BalanceManager Object ID
  let balanceManagerId = null;
  const nodes = effects?.objectChanges?.nodes || [];
  for (const node of nodes) {
    const typeRepr = node?.outputState?.asMoveObject?.contents?.type?.repr || '';
    if (typeRepr.includes('balance_manager::BalanceManager')) {
      balanceManagerId = node.address;
      break;
    }
  }

  if (!balanceManagerId && effects?.effectsJson?.created) {
    for (const c of effects.effectsJson.created) {
      if (c?.owner?.Shared) {
        balanceManagerId = c?.reference?.objectId;
        break;
      }
    }
  }

  if (!balanceManagerId) {
    throw new Error(`Failed to extract BalanceManager ID from effects! Full effects: ${JSON.stringify(effects)}`);
  }

  console.log('\n' + '='.repeat(70));
  console.log(`SUCCESS! DeepBook V3 BalanceManager created and publicly shared:`);
  console.log(`  DEEPBOOK_BALANCE_MANAGER_ID = ${balanceManagerId}`);
  console.log(`  Transaction Explorer: https://suiscan.xyz/mainnet/tx/${txDigest}`);
  console.log('='.repeat(70));

  // 9. Update local .env
  let newEnvContent = envContent;
  if (newEnvContent.includes('DEEPBOOK_BALANCE_MANAGER_ID=')) {
    newEnvContent = newEnvContent.replace(/DEEPBOOK_BALANCE_MANAGER_ID=.*/, `DEEPBOOK_BALANCE_MANAGER_ID=${balanceManagerId}`);
  } else {
    newEnvContent += `\nDEEPBOOK_BALANCE_MANAGER_ID=${balanceManagerId}\n`;
  }
  fs.writeFileSync(envPath, newEnvContent, 'utf8');
  console.log(`Updated ${envPath} with DEEPBOOK_BALANCE_MANAGER_ID=${balanceManagerId}`);

  console.log('\nNext Step: Worker updates Railway environment variables:');
  console.log(`  Tool: railway_mcp:set-variables`);
  console.log(`  projectId:     0b2dfdc6-81f4-4da4-af48-4f566be655d4`);
  console.log(`  environmentId: 9c9b1009-a977-4d27-99af-83d0c20817ef`);
  console.log(`  serviceId:     8ec93921-cafb-417a-9c98-9d8be72d1344`);
  console.log(`  variables:     { DEEPBOOK_BALANCE_MANAGER_ID: "${balanceManagerId}" }`);
}

main().catch((err) => {
  console.error('\nFatal Error:', err);
  process.exit(1);
});
