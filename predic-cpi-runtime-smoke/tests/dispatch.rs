use solana_program::{account_info::AccountInfo, entrypoint::ProgramResult,
    instruction::{AccountMeta,Instruction}, program::invoke, pubkey::Pubkey};
use solana_program_test::{processor,ProgramTest};
use solana_sdk::{signature::Signer,transaction::Transaction};

const PREDIC: Pubkey = solana_program::pubkey!("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb");
const CALLER: Pubkey = solana_program::pubkey!("CpiProbe1111111111111111111111111111111111");

// Native caller intentionally forwards only the pReDic program account.
// This checks runtime loader and CPI dispatch, NOT a valid OPEN.
// It must fail inside the callee rather than be silently treated as success.
fn process(_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    let instruction = Instruction {
        program_id: PREDIC,
        accounts: vec![],
        data: data.to_vec(),
    };
    invoke(&instruction, accounts)
}

#[tokio::test]
async fn cpi_dispatch_into_deployed_elf() {
    let mut test = ProgramTest::new("predictions", PREDIC, None);
    test.add_program("native_cpi_probe", CALLER, processor!(process));
    test.set_compute_max_units(1_000_000);
    let mut ctx = test.start_with_context().await;
    let mut data = [0u8;80];
    data[0..8].copy_from_slice(&64u64.to_le_bytes());
    data[16]=b'Y';
    let ix = Instruction{
        program_id: CALLER,
        accounts: vec![AccountMeta::new_readonly(PREDIC,false)],
        data: data.to_vec(),
    };
    let tx = Transaction::new_signed_with_payer(
        &[ix], Some(&ctx.payer.pubkey()), &[&ctx.payer], ctx.last_blockhash
    );
    let result = ctx.banks_client.process_transaction(tx).await;
    // Invalid OPEN fixtures MUST NOT succeed; a zero-account CPI cannot open an order.
    assert!(result.is_err(), "Invalid fixture unexpectedly succeeded");
    println!("Experimental CPI dispatch produced expected rejection: {:?}", result.err());
    println!("This does not demonstrate successful OPEN or signer-PDA compatibility.");
}
